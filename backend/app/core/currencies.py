"""T3.11.07 — the currencies an account can price in.

A closed list, and short. A typo in a currency code is a price nobody can
compare, and this is the one field on a trip where free text buys nothing: a
carrier quoting in something not here is telling us to add a line, not to accept
`RUUB`.

Held in code rather than in a JSON file beside the postal and payment
catalogues, because unlike those two it is not country-scoped, does not grow
with every corridor, and is used for **validation** — a list the API refuses
values against belongs where the refusal is written.

Ordered alphabetically by code (owner's decision 2026-09-06). Any other order —
by region, by how common, by our own traffic — is an opinion the reader has to
learn before they can find their currency; the alphabet is one they already
know. The stablecoins and cryptocurrencies sit in that same order rather than in
a section of their own: to somebody who prices in USDT it is a currency, not a
category.

Names and one-line descriptions live in the locale files, not here: they are
read by people and have to be translated.
"""

from __future__ import annotations

CURRENCIES: tuple[str, ...] = (
    "AED",
    "BTC",
    "CNY",
    "EUR",
    "GBP",
    "GEL",
    "ILS",
    "INR",
    "KZT",
    "MXN",
    "PLN",
    "RSD",
    "RUB",
    "THB",
    "TRY",
    "UAH",
    "USD",
    "USDC",
    "USDT",
    "UZS",
    "ZEC",
)

# How many an account may keep as its own. Enough for somebody working three
# corridors and settling in a stablecoin, few enough that the trip form can show
# them as chips rather than as a second dropdown.
MAX_ACCOUNT_CURRENCIES = 8
