# Google sign-in for personal accounts

Courtside uses Google's OpenID Connect authorization-code flow. The server checks the signed Google ID token and uses its stable `sub` identifier for the account. Each new Google user gets a private workspace. Existing password accounts are never linked only because an email address matches; sign in with the password first and choose **Link Google account** from the account menu.

## Create the Google credentials

1. In the [Google Cloud Console](https://console.cloud.google.com/), create or select a project. Configure its OAuth consent screen in [Google Auth Platform](https://console.cloud.google.com/auth/overview). Add test users while the app is in Testing status; follow Google's publishing and verification requirements before inviting the public.
2. In [Clients](https://console.cloud.google.com/auth/clients), create an **OAuth client ID** of type **Web application**.
3. Add the exact **Authorized redirect URI** for your Courtside address. For local development on the built app, use `http://localhost:8000/api/auth/google/callback` and open Courtside at `http://localhost:8000`. For a public site, use `https://your-domain.example/api/auth/google/callback`. The scheme, host, port, and path must match.
4. Copy the client ID and client secret into server environment variables. Never put the secret in browser code, Git, or a public `.env` file. Courtside requests only `openid email profile`; it does not request Drive or other Google data.

```powershell
$env:COURTSIDE_AUTH_MODE = 'personal'
$env:COURTSIDE_ORIGIN = 'http://localhost:8000'
$env:COURTSIDE_GOOGLE_CLIENT_ID = 'YOUR_CLIENT_ID.apps.googleusercontent.com'
$env:COURTSIDE_GOOGLE_CLIENT_SECRET = 'YOUR_CLIENT_SECRET'
courtside serve
```

Open `http://localhost:8000/#sessions` in a normal browser and select **Continue with Google**. The Google button appears only when both credentials and the origin are configured. Google may reject embedded browser views; use the device's regular browser in that case. A login creates a server-side session cookie. Google tokens are not stored or sent to the Watch.

## Production host

Use a domain you control with HTTPS, and set `COURTSIDE_ENV=production` and `COURTSIDE_ORIGIN=https://your-domain.example` in the server environment. Register that exact callback URL in the production Google OAuth client. Run `courtside serve` on `127.0.0.1:8000` behind a trusted HTTPS reverse proxy. Preserve the public `Host` and `X-Forwarded-Proto` headers, allow WebSocket upgrades, restrict access to the backend port, and configure Uvicorn to trust only that proxy's forwarded headers. Back up the private storage volume, including account and workspace databases, before changing host or identity settings. Use a separate OAuth client for local tests and production.

The app rejects personal sign-in attempts over plain HTTP from a remote client and will not start in `local` or shared `academy` mode when `COURTSIDE_ENV=production`. Google credentials are required for self-service Google account creation. If they are absent, only password accounts created through local initial setup can sign in. Existing shared recordings remain in their original folder until deliberately assigned to a user; changing the auth mode does not publish them.

These steps configure authentication and data separation. Public release still requires the tennis validation, privacy, licensing, and operational checks in [deployment](deployment.md).

Google references: [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server), [OpenID Connect ID-token validation](https://developers.google.com/identity/openid-connect/openid-connect), and [production OAuth policies](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance).
