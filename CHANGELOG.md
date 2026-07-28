# Changelog

## Unreleased
- Fix: Add local registration view (procurement/register_view.py) and point /register/ URL to it to avoid missing top-level accounts package on deploy.
- Test: Add URL resolution test for register route (procurement/tests/test_urls.py).
- CI: Add GitHub Actions workflow to run Django tests on push/PR.
