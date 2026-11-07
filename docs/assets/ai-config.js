// Configuração da IA do LuaStudio Docs.
// Segurança: não coloque uma chave privada em arquivos públicos do site.
window.LS_AI_CONFIG = {
  provider: "gemini", // gemini | openai | anthropic
  apiKey: "",
  endpoint: "", // vazio = endpoint padrão do provedor
  model: "gemini-flash-latest",
  models: ["gemini-flash-latest", "gemini-2.5-flash"],
  temperature: 0.3,
  maxOutputTokens: 8192,
  topK: 8,
  maxContextChars: 15000
};
