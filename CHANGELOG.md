## Changelog

Notable changes to fun-cli are documented here.
## v1.0.1
- Fixed AI requests failing with HTTP 403 / Cloudflare error 1010 by sending a proper `User-Agent` header.
- Updated the default Groq model from `llama-3.3-70b-versatile` (retired) to `openai/gpt-oss-120b`.
- Clearer error messages now distinguish firewall blocks from invalid API keys.

## v1.0.0
- Significant upgrade.
- Modular layout and install/uninstall support.
- Tests added.

## v0.2.0
- Animated UI and dashboard.
- AI companion tab.

## v0.1.0
- Initial Tkinter MVP.
