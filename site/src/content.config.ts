import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// EDITORIAL layer. The facts layer (src/data/facts/*.json) is machine-owned
// by scripts/refresh-facts.mjs; these schemas cover only what humans write.

const games = defineCollection({
  loader: glob({ pattern: '*.md', base: './src/content/games' }),
  schema: z.object({
    title: z.string(),
    // one-line hook under the title in the hero — ours, not Play's
    hook: z.string().max(120),
    // accent pulled from the game's own key art
    accent: z.string().regex(/^#[0-9a-fA-F]{6}$/),
    // the single editorial stance line ("Why you should play")
    stance: z.string(),
    features: z
      .array(
        z.object({
          title: z.string(),
          body: z.string(),
          // index into facts.screenshots for the card image
          shot: z.number().int().min(0).max(7),
        })
      )
      .length(3),
    faq: z
      .array(z.object({ q: z.string(), a: z.string() }))
      .min(4)
      .max(6),
    related: z.array(z.string()).length(3), // slugs
    collectionSlug: z.string().optional(),  // the "From the collection" banner
    order: z.number().default(99),          // home page shelf ordering
  }),
});

const gameCollections = defineCollection({
  loader: glob({ pattern: '*.md', base: './src/content/collections' }),
  schema: z.object({
    title: z.string(),
    deck: z.string(), // one-paragraph standfirst
    accent: z.string().regex(/^#[0-9a-fA-F]{6}$/),
    games: z.array(z.string()).min(3), // ordered slugs
  }),
});

export const collections = { games, collections: gameCollections };
