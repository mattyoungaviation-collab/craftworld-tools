import { z } from 'zod';

export const factoryRowSchema = z.object({
  token: z.string().min(1),
  level: z.coerce.number().int().nonnegative(),
  duration_min: z.coerce.number().nonnegative(),
  output_token: z.string().optional().nullable(),
  output_amount: z.coerce.number().nonnegative(),
  input_token_1: z.string().optional().nullable(),
  input_amount_1: z.coerce.number().optional().nullable(),
  input_token_2: z.string().optional().nullable(),
  input_amount_2: z.coerce.number().optional().nullable(),
  upgrade_token: z.string().optional().nullable(),
  upgrade_amount: z.coerce.number().optional().nullable()
});

export type FactoryRow = z.infer<typeof factoryRowSchema>;
