import { handle, type Env } from "./app.ts";

export default {
  fetch: (request: Request, env: Env) => handle(request, env),
};
