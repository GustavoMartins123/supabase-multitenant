import { z } from 'zod'

export const privilegeSchema = z.object({
  operation: z.enum(['grant', 'revoke']),
  tables: z.array(z.string().regex(/^[a-zA-Z_][a-zA-Z0-9_]*$/).max(63)).min(1).max(20),
  role: z.enum(['anon', 'authenticated']),
  privileges: z.array(z.enum(['SELECT', 'INSERT', 'UPDATE', 'DELETE'])).min(1).max(4),
  label: z.string().min(1).max(100),
}).strict().refine(input => new Set(input.tables).size === input.tables.length
  && new Set(input.privileges).size === input.privileges.length, 'Specify each table and privilege exactly once')

export function privilegeSql(input) {
  const change = privilegeSchema.parse(input)
  const tables = change.tables.map(table => `public."${table}"`).join(', ')
  const privileges = change.privileges.join(', ')
  return change.operation === 'grant'
    ? `GRANT ${privileges} ON TABLE ${tables} TO "${change.role}";`
    : `REVOKE ${privileges} ON TABLE ${tables} FROM "${change.role}" RESTRICT;`
}
