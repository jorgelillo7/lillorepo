export interface Statement {
  bind(...values: unknown[]): Statement;
  run(): Promise<{ meta: { changes: number } }>;
  all<T>(): Promise<{ results: T[] }>;
}

export interface Database {
  prepare(sql: string): Statement;
  /** Run the statements in order inside one transaction: all of them apply, or none. */
  batch(statements: Statement[]): Promise<{ meta: { changes: number } }[]>;
}

export interface Env {
  DB: Database;
  ASSETS: { fetch(request: Request): Promise<Response> };
  ADMIN_USER?: string;
  ADMIN_PASSWORD?: string;
}
