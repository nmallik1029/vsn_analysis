import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  STOCK_ANALYZER_CONTAINER: DurableObjectNamespace<StockAnalyzerContainer>;
  SUPABASE_URL?: string;
  SUPABASE_ANON_KEY?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  SECRET_KEY?: string;
  MODERATOR_EMAILS?: string;
  MODERATOR_IDS?: string;
  CLOUDFLARE_API_TOKEN?: string;
  CLOUDFLARE_ACCOUNT_ID?: string;
  CLOUDFLARE_SITE_TAG?: string;
  LLM_PROVIDER?: string;
  OPENAI_API_KEY?: string;
  OPENAI_MODEL?: string;
  GEMINI_API_KEY?: string;
  GEMINI_MODEL?: string;
}

export class StockAnalyzerContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "10m";
  requiredPorts = [8080];

  override envVars = {
    SUPABASE_URL: this.env.SUPABASE_URL ?? "",
    SUPABASE_ANON_KEY: this.env.SUPABASE_ANON_KEY ?? "",
    SUPABASE_SERVICE_ROLE_KEY: this.env.SUPABASE_SERVICE_ROLE_KEY ?? "",
    SECRET_KEY: this.env.SECRET_KEY ?? "",
    MODERATOR_EMAILS: this.env.MODERATOR_EMAILS ?? "",
    MODERATOR_IDS: this.env.MODERATOR_IDS ?? "",
    CLOUDFLARE_API_TOKEN: this.env.CLOUDFLARE_API_TOKEN ?? "",
    CLOUDFLARE_ACCOUNT_ID: this.env.CLOUDFLARE_ACCOUNT_ID ?? "",
    CLOUDFLARE_SITE_TAG: this.env.CLOUDFLARE_SITE_TAG ?? "",
    LLM_PROVIDER: this.env.LLM_PROVIDER ?? "",
    OPENAI_API_KEY: this.env.OPENAI_API_KEY ?? "",
    OPENAI_MODEL: this.env.OPENAI_MODEL ?? "",
    GEMINI_API_KEY: this.env.GEMINI_API_KEY ?? "",
    GEMINI_MODEL: this.env.GEMINI_MODEL ?? "",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const container = getContainer(env.STOCK_ANALYZER_CONTAINER, "singleton");
    return container.fetch(request);
  },
} satisfies ExportedHandler<Env>;
