import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const biblioteca = defineCollection({
  loader: glob({ pattern: '**/[^_]*.{md,mdx}', base: './src/content/biblioteca' }),
  schema: z.object({
    title: z.string(),
    disciplina: z.string(),
    ano: z.number(),
    semestre: z.number(),
    tipo: z.string(),
    fonte_original: z.string(),
    confianca_media: z.number(),
    data_processamento: z.string(),
    storage_url: z.string().nullable().optional(),
    hash: z.string()
  })
});

export const collections = { biblioteca };
