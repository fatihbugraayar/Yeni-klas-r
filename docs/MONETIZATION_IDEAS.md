# Commercial product ideas — proposed, not implemented

This document records the monetization discussion after the AI Grid Studio 1.1 implementation.
It is input for the knowledge graph, not an instruction to implement or launch these features.
Demand, pricing, production costs and commercial returns have not been validated.

## Current product

The implemented bot has three independent quota pools:

- Direct custom emoji splitter: 2×2–8×8, three lifetime free packs, then 50 Stars.
- Face censorship: five lifetime uses plus one non-accumulating daily UTC use, then 20 Stars.
- AI Grid Studio: 1×1–9×9 blueprints and TR/EN/DE prompts, one lifetime free pack,
  then 100 Stars for either custom emoji or regular sticker output.

AI Grid Studio currently asks the user to generate artwork in an external tool and upload it.
The bot draws the layout and packages the uploaded artwork; it does not call an AI image API.

## Proposal 1: Personalized reaction packs

Let a user upload a personal or pet photo and receive twelve distinct reaction stickers with
consistent character identity. Generation inside the bot would reduce the current external-tool
steps. A possible initial offer is 249 Stars with one correction included. This is a test price,
not a market benchmark or a claim of profitability. This feature is not implemented.

## Proposal 2: Brand and channel packs

Create twenty-four stickers using a business logo, brand colors and mascot for greetings,
thanks, announcements and reactions. A possible pilot offer is 1,499 Stars with two corrections.
This is an unvalidated test price. This feature is not implemented.

## Proposal 3: Studio editing tools

Add individual-cell replacement, correction of misaligned grid cuts and batch background cleanup.
These would support the personalized and brand offers. Existing white backgrounds currently
remain white; automatic background removal and per-cell regeneration are not implemented.

## Proposal 4: Repeat-purchase subscriptions

Store characters and brand profiles, update existing packs and offer a monthly pack allowance
after repeat purchases demonstrate demand. Cap generation and correction credits to control
variable AI costs. Unlimited AI generation is not the proposed launch model. Profiles, pack
updates and subscriptions are not implemented.

## Commercial validation and cost accounting

Begin with a small manually fulfilled paid pilot of personalized and brand packs before investing
in full automation. Measure paid demand and repeat purchases. Add an operator dashboard for
production cost per order, payment conversion, repeat purchases and refunds. These analytics
are proposed; the current transaction ledger records payments but is not a commercial dashboard.

Assess contribution per order using actual net payout minus AI generation and retry costs,
server allocation, support, customer acquisition and refunds. Include fixed costs and taxes
when assessing overall profit. A user's purchase price for Stars is not automatically the
seller's net cash revenue. No exact exchange rate or expected margin is assumed here.

Telegram provides a built-in sticker editor with creation and background removal. The commercial
hypothesis is that personalization, consistent design and batch production provide a stronger
reason to pay than simple packaging alone; this inference still needs a paid pilot.

## Sources and constraints

- Telegram's existing sticker editor: https://telegram.org/blog/sticker-maker?setln=en
- Digital goods sold inside Telegram use Stars (XTR): https://core.telegram.org/bots/payments-stars
- Telegram supports bot subscription models: https://core.telegram.org/bots/features#subscription-plans

These links support platform capabilities and payment constraints, not demand or proposed prices.
The proposals do not authorize external messages, purchases, live payments or deployment.
