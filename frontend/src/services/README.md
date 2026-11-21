# API services

`apiClient.ts` handles JSON GET requests, timeouts, cancellation, and HTTP errors.
Endpoint modules such as `health.ts` own their response types and validate payloads
before returning them to UI components.
