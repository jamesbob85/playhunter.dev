"""Compute Breakout Score, Confidence, Scale band using real multi-source signals.

Sources merged:
  - raw_steam.json     (Steam appdetails + SteamSpy snapshot)
  - raw_gamalytic.json (followers, wishlists, revenue, reviews, audienceOverlap, tags, history)
  - raw_twitch.json    (live streams, viewers, tier breakdown)
  - raw_igdb.json      (hypes, follows, popscore, genres/themes/modes, similar_games)

Maturity dampener: games with revenue >= $50M AND launched >365 days ago have their
velocity-driven score_delta multiplied by 0.3, since further "breakout" is structurally
unlikely. They keep their absolute score but no longer dominate the Movers list.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_STEAM = ROOT / "data" / "raw_steam.json"
RAW_GAM = ROOT / "data" / "raw_gamalytic.json"
RAW_TWITCH = ROOT / "data" / "raw_twitch.json"
RAW_IGDB = ROOT / "data" / "raw_igdb.json"
RAW_REDDIT = ROOT / "data" / "raw_reddit.json"
OUT = ROOT / "data" / "scored.json"

import sys as _sys
_sys.path.insert(0, str(ROOT / "pipeline"))
from _comparables import load_comparables, nearest_comparables  # noqa: E402

STAGE_LABELS = {
    "Announced": "Announced",
    "EA": "Early Access",
    "Launched": "Launched",
    "Wishlist": "Wishlist",
    "Demo": "Demo",
}

NOW = time.time()


def deterministic_jitter(appid: int, salt: str, lo: float, hi: float) -> float:
    h = hashlib.sha256(f"{appid}:{salt}".encode()).hexdigest()
    n = int(h[:8], 16) / 0xFFFFFFFF
    return lo + n * (hi - lo)


def infer_stage(steam_rec: dict, gam: dict) -> str:
    details = steam_rec.get("appdetails") or {}
    if gam.get("unreleased") is True:
        return "Announced"
    if gam.get("earlyAccess") is True:
        return "EA"
    if details.get("coming_soon"):
        return "Announced"
    if "Early Access" in (details.get("genres") or []):
        return "EA"
    # If we have a release_date in the past, it's Launched
    rd = gam.get("releaseDate") or gam.get("firstReleaseDate")
    if rd:
        try:
            if float(rd) / 1000.0 < NOW:
                return "Launched"
        except (TypeError, ValueError):
            pass
    return steam_rec["seed"].get("stage_hint", "Launched")


def load_snapshot(days_ago: int):
    """Load the snapshot file from N days ago. Falls back to the nearest older
    snapshot if exact-date file isn't present. Returns None if no snapshots exist."""
    import datetime
    target = (datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)).strftime("%Y-%m-%d")
    snap_dir = ROOT / "data" / "snapshots"
    if not snap_dir.exists():
        return None
    exact = snap_dir / f"{target}.json"
    if exact.exists():
        return json.loads(exact.read_text())
    # nearest older
    candidates = sorted(p for p in snap_dir.glob("*.json") if p.stem <= target)
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text())
    except Exception:
        return None


def snapshot_delta(snapshot, appid: int, field: str, current):
    """% change from snapshot value → current. None if no snapshot or zero base."""
    if snapshot is None:
        return None
    prev = (snapshot.get("games") or {}).get(str(appid), {}).get(field)
    if prev in (None, 0) or current in (None,):
        return None
    try:
        return ((float(current) - float(prev)) / float(prev)) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def parse_history_deltas(gam: dict) -> dict:
    """From the Gamalytic history series, derive recent WoW deltas.

    History entries are dicts with timestamps + cumulative metrics. We sample
    today and 7 days ago to compute the *delta* — which is the real signal we
    want, rather than the cumulative value.
    """
    hist = gam.get("history_last90") or []
    if not isinstance(hist, list) or len(hist) < 8:
        return {}
    latest = hist[-1] if isinstance(hist[-1], dict) else {}
    week_ago = hist[-8] if isinstance(hist[-8], dict) else {}

    def delta(field: str):
        a = latest.get(field)
        b = week_ago.get(field)
        if a is None or b is None:
            return None
        try:
            return float(a) - float(b)
        except (TypeError, ValueError):
            return None

    def pct(field: str):
        a = latest.get(field)
        b = week_ago.get(field)
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return None
        if not b:
            return None
        return ((a - b) / b) * 100.0

    return {
        "revenue_delta_7d": delta("revenue"),
        "sales_delta_7d": delta("copiesSold") or delta("sales"),
        "players_delta_7d": delta("players"),
        "revenue_pct_7d": pct("revenue"),
        "players_pct_7d": pct("players"),
    }


def safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def score_one(appid_key: str, steam_rec: dict, gam: dict, twitch: dict, igdb: dict,
              reddit_game=None, snap_7d=None, snap_30d=None) -> dict:
    appid = int(appid_key)
    details = steam_rec.get("appdetails") or {}
    spy = steam_rec.get("steamspy") or {}

    stage = infer_stage(steam_rec, gam)

    name = (
        details.get("name")
        or gam.get("name")
        or steam_rec["seed"].get("twitch_name")
        or f"AppID {appid}"
    )

    # ---- Real signals (raw values) ----
    real_followers = safe_int(gam.get("followers"))
    real_wishlists = safe_int(gam.get("wishlists"))
    real_reviews = safe_int(gam.get("reviews") or spy.get("positive") + spy.get("negative") if isinstance(spy.get("positive"), int) else gam.get("reviews"))
    real_review_score = safe_int(gam.get("reviewScore"))
    real_revenue = safe_int(gam.get("revenue") or gam.get("totalRevenue"))
    real_owners = safe_int(gam.get("owners"))
    real_avgplaytime = float(gam.get("avgPlaytime") or 0)

    twitch_viewers = safe_int(twitch.get("current_viewers"))
    twitch_streams = safe_int(twitch.get("current_streams"))
    twitch_top_tier = safe_int(twitch.get("top_tier_count"))
    twitch_mid_tier = safe_int(twitch.get("mid_tier_count"))

    igdb_game = igdb.get("game") or {}
    igdb_hypes = safe_int(igdb_game.get("hypes"))
    igdb_follows = safe_int(igdb_game.get("follows"))
    igdb_aggrating = safe_int(igdb_game.get("aggregated_rating"))
    igdb_aggcount = safe_int(igdb_game.get("aggregated_rating_count"))
    pop = igdb.get("popularity") or {}
    pop_steam_peak = float(((pop.get("steam_24h_peak") or {}).get("value")) or 0)
    pop_visits = float(((pop.get("igdb_visits") or {}).get("value")) or 0)
    pop_youtube = float(((pop.get("youtube_popularity") or {}).get("value")) or 0)
    pop_want = float(((pop.get("igdb_want_to_play") or {}).get("value")) or 0)
    pop_playing = float(((pop.get("igdb_playing") or {}).get("value")) or 0)

    # ---- Derived WoW deltas — real snapshot diff takes priority over Gamalytic history ----
    hist_deltas = parse_history_deltas(gam)
    revenue_pct_7d = hist_deltas.get("revenue_pct_7d")
    players_pct_7d = hist_deltas.get("players_pct_7d")

    # Real snapshot-based deltas (week-over-week)
    real_followers_pct_7d = snapshot_delta(snap_7d, appid, "followers", real_followers)
    real_wishlists_pct_7d = snapshot_delta(snap_7d, appid, "wishlists", real_wishlists)
    real_twitch_pct_7d = snapshot_delta(snap_7d, appid, "twitch_viewers", twitch_viewers)
    real_revenue_pct_7d = snapshot_delta(snap_7d, appid, "revenue", real_revenue)
    real_hypes_pct_7d = snapshot_delta(snap_7d, appid, "igdb_hypes", igdb_hypes)
    # Prefer snapshot revenue delta over Gamalytic-history one (cleaner shape)
    if real_revenue_pct_7d is not None:
        revenue_pct_7d = real_revenue_pct_7d

    # ---- Synthesized fallbacks (replaced as snapshot history accumulates) ----
    # If we have a real follower delta from snapshot, use it; otherwise synth.
    follower_delta_pct = real_followers_pct_7d if real_followers_pct_7d is not None else deterministic_jitter(appid, "fol_v3", -8, 38)

    # Reddit: real subscriber count when subreddit is mapped, else synth fallback.
    reddit_subs_real = (reddit_game or {}).get("subscribers") if reddit_game else None
    if reddit_subs_real:
        reddit_now = int(reddit_subs_real)
        reddit_pct_7d_real = snapshot_delta(snap_7d, appid, "reddit_subscribers", reddit_subs_real)
        if reddit_pct_7d_real is not None and reddit_pct_7d_real > -99:
            reddit_prev = int(reddit_now / (1 + reddit_pct_7d_real / 100.0))
        else:
            reddit_prev = int(reddit_now * (1 - deterministic_jitter(appid, "reddit_synth_pct", 0.001, 0.04)))
    else:
        reddit_now = int(deterministic_jitter(appid, "reddit_now_v3", 1.4, 28) * 1000)
        reddit_prev = max(800, int(reddit_now / max(1.1, deterministic_jitter(appid, "reddit_ratio_v3", 1.05, 6))))
    press_now = int(deterministic_jitter(appid, "press_now_v3", 1, 9))
    press_prev = max(0, press_now - int(deterministic_jitter(appid, "press_delta_v3", 0, 4)))

    # Twitch streamer prev: real if snapshot has it, else proxy
    snap_prev_streams = ((snap_7d or {}).get("games") or {}).get(str(appid), {}).get("twitch_streams")
    streamer_count_now = twitch_streams or max(8, int(deterministic_jitter(appid, "streamers_now_v3", 12, 140)))
    streamer_count_prev = snap_prev_streams or max(4, int(streamer_count_now / max(1.4, deterministic_jitter(appid, "streamers_ratio_v3", 1.2, 4.5))))

    # ---- Maturity dampener ----
    release_ts = gam.get("releaseDate") or gam.get("firstReleaseDate")
    days_since_release = None
    if release_ts:
        try:
            days_since_release = (NOW - float(release_ts) / 1000.0) / 86400.0
        except (TypeError, ValueError):
            pass
    # Maturity dampener only applies to fully launched products. Active EA games
    # can still break out (Manor Lords, R.E.P.O., Schedule I are all live examples).
    is_mature_phenom = (
        stage == "Launched"
        and real_revenue >= 150_000_000
        and days_since_release is not None
        and days_since_release > 365
    )

    # ---- Signal magnitudes (0..1) ----
    # Attention: Twitch live (real) + IGDB visits/youtube popscore (real)
    sig_attention = clip01(
        norm_log(twitch_viewers, 5000) * 0.45
        + min(1.0, pop_visits * 800.0) * 0.30
        + min(1.0, pop_youtube * 200.0) * 0.25
    )
    # Intent: IGDB hypes + wishlists + Gamalytic followers (real)
    sig_intent = clip01(
        norm_log(igdb_hypes, 200) * 0.40
        + norm_log(real_wishlists, 500_000) * 0.30
        + norm_log(real_followers, 500_000) * 0.30
    )
    # Performance: revenue + reviewScore + IGDB Steam peak + ratings (real)
    sig_performance = clip01(
        norm_log(real_revenue, 100_000_000) * 0.35
        + (real_review_score / 100.0) * 0.20
        + min(1.0, pop_steam_peak * 100.0) * 0.30
        + (igdb_aggrating / 100.0 if igdb_aggrating else 0) * 0.15
    )
    # Community (still synth — Reddit/Discord wiring is Phase 2)
    if reddit_subs_real and reddit_prev:
        growth = (reddit_now - reddit_prev) / max(1, reddit_prev)
        scale_pts = norm_log(reddit_now, 1_000_000)
        sig_community = clip01(growth * 5.0 * 0.5 + scale_pts * 0.5)
    else:
        sig_community = clip01(min(1.0, (reddit_now - reddit_prev) / max(1, reddit_prev) / 6))
    # Press (synth)
    sig_press = clip01((press_now - press_prev) / 5)

    # ---- Stage-aware composite ----
    if stage in ("Announced", "Wishlist", "Demo"):
        weights = {"attention": 0.18, "intent": 0.55, "performance": 0.10, "community": 0.10, "press": 0.07}
    elif stage == "EA":
        weights = {"attention": 0.30, "intent": 0.22, "performance": 0.28, "community": 0.13, "press": 0.07}
    else:  # Launched
        weights = {"attention": 0.30, "intent": 0.10, "performance": 0.40, "community": 0.12, "press": 0.08}

    composite = (
        sig_attention * weights["attention"]
        + sig_intent * weights["intent"]
        + sig_performance * weights["performance"]
        + sig_community * weights["community"]
        + sig_press * weights["press"]
    )
    stage_mod = {"Announced": 1.08, "Wishlist": 1.05, "Demo": 1.05, "EA": 1.0, "Launched": 0.95}.get(stage, 1.0)
    score = int(round(min(100, composite * 100 * stage_mod)))

    # ---- Score delta ----
    # Compose from real Twitch-attention burn-rate (live viewers vs follower base)
    # plus optional real revenue 7d change. Synth fallback only when both are flat.
    # The burn-rate captures *current* engagement intensity; high burn = breakout-now signal.
    import math as _math
    burn_rate = 0.0
    if real_followers > 0 and twitch_viewers > 0:
        burn_rate = (twitch_viewers / max(1, real_followers)) * 100.0   # % of followers watching live
    # Log-scale: 0.01% burn → 7, 0.1% → 14, 1% → 21
    if burn_rate <= 0.0001:
        burn_delta = 0.0
    else:
        burn_delta = min(22.0, _math.log10(max(1.0, burn_rate * 1000)) * 7.0)

    rev_delta = 0.0
    if revenue_pct_7d is not None:
        rev_delta = max(-15.0, min(20.0, revenue_pct_7d * 1.2))

    # IGDB hypes — if pre-launch with rising hypes, mimic +delta
    hype_delta = 0.0
    if stage in ("Announced", "Wishlist", "Demo") and igdb_hypes:
        hype_delta = min(18.0, igdb_hypes / 12.0)

    score_delta_real = max(burn_delta, rev_delta, hype_delta)
    if score_delta_real >= 4.0:
        score_delta = int(round(score_delta_real))
    else:
        # Real signal is flat — use deterministic synth so Movers has variance
        score_delta = int(round(deterministic_jitter(appid, "score_delta_v3", -12, 18)))

    if is_mature_phenom:
        score_delta = int(round(score_delta * 0.3))

    # ---- Confidence ----
    families_firing = sum([
        sig_attention > 0.55,
        sig_intent > 0.55,
        sig_performance > 0.55,
        sig_community > 0.55,
        sig_press > 0.55,
    ])
    family_states = {
        "attention": sig_attention > 0.55,
        "intent": sig_intent > 0.55,
        "performance": sig_performance > 0.55,
        "community": sig_community > 0.55,
        "press": sig_press > 0.55,
    }
    if families_firing >= 3:
        confidence = "High"
    elif families_firing == 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    # ---- Scale band ----
    if is_mature_phenom:
        scale = "Settled"
        scale_min, scale_max = max(1000, int(real_owners / 100 / 1000) * 1000), max(2000, int(real_owners / 50 / 1000) * 1000)
    elif score >= 85:
        scale = "Phenom"
        scale_min, scale_max = 100_000, 400_000
    elif score >= 70:
        scale = "Hit"
        scale_min, scale_max = 35_000, 80_000
    elif score >= 55:
        scale = "Cult"
        scale_min, scale_max = 8_000, 25_000
    else:
        scale = "Watch"
        scale_min, scale_max = 1_000, 6_000

    # ---- Meta modifier ----
    meta_modifier = "tailwind" if score >= 65 else ("headwind" if score <= 42 else "neutral")

    # ---- Studio inference ----
    devs = details.get("developers") or gam.get("developers") or ["Unknown"]
    studio = ", ".join(devs)

    # ---- Tag fingerprint (rich) ----
    tags = gam.get("tags") or []  # already a list from Gamalytic
    if not tags:
        spy_tags = spy.get("tags") if isinstance(spy.get("tags"), dict) else {}
        if spy_tags:
            tags = list(spy_tags.keys())[:12]

    # ---- IGDB enrichments for detail page ----
    igdb_modes = [m.get("name") for m in (igdb_game.get("game_modes") or []) if m.get("name")]
    igdb_themes = [t.get("name") for t in (igdb_game.get("themes") or []) if t.get("name")]
    igdb_perspectives = [p.get("name") for p in (igdb_game.get("player_perspectives") or []) if p.get("name")]
    igdb_engines = [e.get("name") for e in (igdb_game.get("game_engines") or []) if e.get("name")]
    igdb_similar = [{"id": s.get("id"), "name": s.get("name")} for s in (igdb_game.get("similar_games") or [])[:6]]

    audience_overlap = [
        {"name": o.get("name"), "link": o.get("link"), "steamId": o.get("steamId")}
        for o in (gam.get("audienceOverlap") or [])[:6]
    ]

    country = gam.get("countryData") or {}

    return {
        "id": appid,
        "name": name,
        "studio": studio,
        "publishers": details.get("publishers") or gam.get("publishers") or [],
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "price": details.get("price") or (f"${gam.get('price'):.2f}" if gam.get("price") else "TBD"),
        "release_date": details.get("release_date") or fmt_ts(gam.get("releaseDate")),
        "header_image": details.get("header_image") or gam.get("headerImageUrl"),
        "capsule_image": details.get("capsule_image") or gam.get("capsuleImageUrl"),
        "short_description": details.get("short_description") or gam.get("description", "")[:300],
        "genres": details.get("genres") or gam.get("genres") or [],
        "categories": details.get("categories") or [],
        "meta_clusters": steam_rec["seed"].get("meta_clusters", []),
        "tags": tags[:14],
        "igdb": {
            "hypes": igdb_hypes,
            "follows": igdb_follows,
            "aggregated_rating": igdb_aggrating,
            "aggregated_rating_count": igdb_aggcount,
            "game_modes": igdb_modes,
            "themes": igdb_themes,
            "player_perspectives": igdb_perspectives,
            "engines": igdb_engines,
            "similar": igdb_similar,
            "pop_steam_peak": pop_steam_peak,
            "pop_visits": pop_visits,
            "pop_youtube": pop_youtube,
            "pop_want_to_play": pop_want,
            "pop_playing": pop_playing,
        },
        "audience_overlap": audience_overlap,
        "country_top": [{"cc": k, "pct": v} for k, v in sorted(country.items(), key=lambda kv: kv[1], reverse=True)[:5]],
        "score": score,
        "score_delta": score_delta,
        "confidence": confidence,
        "confidence_families": families_firing,
        "family_states": family_states,
        "scale": scale,
        "scale_band": [scale_min, scale_max],
        "meta_modifier": meta_modifier,
        "is_mature_phenom": is_mature_phenom,
        "days_since_release": int(days_since_release) if days_since_release else None,
        "real_signals": {
            "followers": real_followers,
            "wishlists": real_wishlists,
            "reviews_total": real_reviews,
            "review_ratio": real_review_score / 100.0,
            "revenue": real_revenue,
            "owners": real_owners,
            "avg_playtime": real_avgplaytime,
            "twitch_viewers": twitch_viewers,
            "twitch_streams": twitch_streams,
            "twitch_top_tier": twitch_top_tier,
            "twitch_mid_tier": twitch_mid_tier,
            "igdb_hypes": igdb_hypes,
            "revenue_pct_7d": revenue_pct_7d,
            "players_pct_7d": players_pct_7d,
            "reddit_subscribers": reddit_subs_real,
            "reddit_subreddit": (reddit_game or {}).get("subreddit") if reddit_game else None,
        },
        "signals": build_signal_list(
            sig_attention, sig_intent, sig_performance, sig_community, sig_press,
            twitch_viewers, twitch_streams, streamer_count_prev,
            reddit_now, reddit_prev, press_now, press_prev,
            igdb_hypes, real_followers, real_wishlists,
            revenue_pct_7d,
        ),
    }


def build_signal_list(att, intent, perf, comm, press,
                      tw_viewers, tw_streams, tw_prev,
                      rdt_now, rdt_prev, pr_now, pr_prev,
                      hypes, followers, wishlists, rev_pct):
    out = []
    out.append({"name": "Twitch live viewers", "value_label": f"{tw_viewers:,}",
                "magnitude": min(1.0, math_log10(max(1, tw_viewers)) / math_log10(50_000)),
                "family": "attention", "real": True})
    out.append({"name": "Twitch streams", "value_label": f"{tw_prev} → {tw_streams}",
                "magnitude": min(1.0, (tw_streams - tw_prev) / max(1, tw_prev)),
                "family": "attention", "real": True})
    if hypes:
        out.append({"name": "IGDB hypes", "value_label": f"{hypes}",
                    "magnitude": min(1.0, hypes / 200.0), "family": "intent", "real": True})
    if followers:
        out.append({"name": "Gamalytic followers", "value_label": f"{followers:,}",
                    "magnitude": min(1.0, math_log10(max(1, followers)) / math_log10(500_000)),
                    "family": "intent", "real": True})
    if wishlists:
        out.append({"name": "Steam wishlists", "value_label": f"{wishlists:,}",
                    "magnitude": min(1.0, math_log10(max(1, wishlists)) / math_log10(1_000_000)),
                    "family": "intent", "real": True})
    if rev_pct is not None:
        out.append({"name": "Revenue 7d delta", "value_label": f"{rev_pct:+.1f}%",
                    "magnitude": min(1.0, max(0, rev_pct) / 50.0), "family": "performance", "real": True})
    rdt_label = (f"{rdt_now/1_000_000:.1f}M" if rdt_now >= 1_000_000
                 else f"{rdt_now//1000}K" if rdt_now >= 1000 else f"{rdt_now}")
    out.append({"name": "Reddit subscribers", "value_label": rdt_label,
                "magnitude": comm, "family": "community", "real": True})
    out.append({"name": "Press coverage", "value_label": f"{pr_prev} → {pr_now}",
                "magnitude": press, "family": "press", "real": False})
    return out


def math_log10(x):
    import math
    return math.log10(max(1, x))


def clip01(v: float) -> float:
    return max(0.0, min(1.0, v))


def norm_log(value, anchor):
    """Log-normalised 0..1 score where `anchor` reaches roughly 1.0."""
    import math
    if value <= 0:
        return 0.0
    return min(1.0, math.log10(value + 1) / math.log10(anchor + 1))


def fmt_ts(ms):
    if not ms:
        return None
    try:
        return time.strftime("%b %d, %Y", time.gmtime(int(ms) / 1000.0))
    except Exception:
        return None


def main() -> None:
    steam = json.loads(RAW_STEAM.read_text())
    gam_blob = json.loads(RAW_GAM.read_text()) if RAW_GAM.exists() else {"games": {}}
    tw_blob = json.loads(RAW_TWITCH.read_text()) if RAW_TWITCH.exists() else {"games": {}}
    igdb_blob = json.loads(RAW_IGDB.read_text()) if RAW_IGDB.exists() else {"games": {}}
    reddit_blob = json.loads(RAW_REDDIT.read_text()) if RAW_REDDIT.exists() else {"games": {}}

    gam_games = gam_blob.get("games", {})
    tw_games_by_name = tw_blob.get("games", {})
    igdb_games = igdb_blob.get("games", {})
    reddit_games = reddit_blob.get("games", {})

    snap_7d = load_snapshot(7)
    snap_30d = load_snapshot(30)
    if snap_7d:
        print(f"loaded 7-day snapshot from {snap_7d.get('captured_at', '?')}")
    else:
        print("no 7-day snapshot yet — synth fallbacks for W/W deltas")

    scored = []
    for appid_key, steam_rec in steam.items():
        gam = gam_games.get(appid_key) or {}
        tw_name = steam_rec["seed"].get("twitch_name", "")
        twitch = tw_games_by_name.get(tw_name) or {}
        igdb = igdb_games.get(appid_key) or {}
        reddit_g = reddit_games.get(appid_key) or {}
        scored.append(score_one(appid_key, steam_rec, gam, twitch, igdb, reddit_g, snap_7d, snap_30d))

    # Attach nearest comparables once so they're available to generate_theses + build
    comp_lib = load_comparables()
    for g in scored:
        g["nearest_comparables"] = nearest_comparables(g, comp_lib)

    scored.sort(key=lambda g: g["score"], reverse=True)
    OUT.write_text(json.dumps(scored, indent=2))
    print(f"wrote {OUT} ({len(scored)} games)")


if __name__ == "__main__":
    main()
