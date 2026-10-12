# Graph Report - Yeni klasör  (2026-10-11)

## Corpus Check
- Corpus is ~14,087 words - fits in a single context window. You may not need a graph.

## Summary
- 407 nodes · 1069 edges · 23 communities (9 shown, 14 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 93 edges (avg confidence: 0.89)
- Token cost: unavailable (host-agent counters are not exposed)

## Community Hubs (Navigation)
- Kota ödeme veritabanı
- Ürün ve gelir planı
- Medya teslimatı testleri
- Görsel işleme ve sansür
- Ana menü ve gezinme
- Stüdyo yükleme akışı
- Şablonlar ve çalışma kilidi
- Dil ve ödeme doğrulama
- Güncelleme ve ödeme kurtarma
- İş ve iade kuyruğu
- Ayarlar ve yapılandırma
- Doğrudan emoji akışı
- Yüz gizleme akışı
- Eski düğme yönetimi
- Fatura açma
- Proje paket bilgisi

## God Nodes (most connected - your core abstractions)
1. `Repository` - 42 edges
2. `MediaStore` - 27 edges
3. `utcnow()` - 24 edges
4. `main()` - 21 edges
5. `new_job()` - 21 edges
6. `Database` - 17 edges
7. `User` - 17 edges
8. `submit()` - 17 edges
9. `test_complete_telegram_routing_free_pack_no_faces_and_paid_recovery()` - 17 edges
10. `Job` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Existing payment transaction ledger — implemented, not a commercial dashboard` --references--> `Transaction`  [INFERRED]
  docs/MONETIZATION_IDEAS.md → telegram_bot/database/models.py
- `Atomic quota reservation and job insertion — implemented` --references--> `Repository`  [INFERRED]
  README.md → telegram_bot/database/repository.py
- `AI Grid Studio — implemented, 1×1–9×9` --references--> `submit()`  [INFERRED]
  README.md → telegram_bot/handlers/upload.py
- `Center-cropped row-major sprite slicing — implemented` --references--> `split_studio_grid()`  [INFERRED]
  README.md → telegram_bot/services/image_service.py
- `Telegram Stars (XTR) digital-goods payments — implemented` --references--> `PaymentService`  [INFERRED]
  README.md → telegram_bot/services/payment_service.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Persistent Compose deployment** — compose_bot, compose_bot_data, compose_restart_policy [EXTRACTED 1.00]
- **Implemented Studio flow: free blueprint/prompt, external generation, upload, selected paid or free output** — readme_ai_studio, readme_blueprint, readme_generation_prompt, readme_external_generation, readme_custom_emoji_output, readme_regular_sticker_output [EXTRACTED 1.00]
- **Implemented payment recovery: persist before offset, idempotent accounting, retry/refund, at-least-once result delivery** — readme_payment_inbox, readme_payment_idempotency, readme_job_recovery, readme_retry_and_refunds, readme_at_least_once_delivery [EXTRACTED 1.00]
- **Proposed commercial validation before automation/subscriptions: pilot offers, demand/cost dashboard, net contribution** — docs_monetization_ideas_paid_pilot, docs_monetization_ideas_personalized_reaction_packs, docs_monetization_ideas_brand_channel_packs, docs_monetization_ideas_operator_dashboard, docs_monetization_ideas_contribution_accounting, docs_monetization_ideas_subscriptions [EXTRACTED 1.00]

## Communities (23 total, 14 thin omitted)

### Community 0 - "Kota ödeme veritabanı"
Cohesion: 0.07
Nodes (25): Database, Base, Job, PaymentInbox, Transaction, User, utcdate(), utcnow() (+17 more)

### Community 1 - "Ürün ve gelir planı"
Cohesion: 0.06
Nodes (49): Docker Compose bot service, Persistent bot_data volume, Environment file .env, no-new-privileges security option, unless-stopped restart policy, Brand and channel packs — proposed, 24 stickers; unvalidated 1,499 Stars pilot offer, Commercial product ideas — proposals only, unvalidated, Integrated AI artwork generation — proposed, not currently called by the bot (+41 more)

### Community 2 - "Medya teslimatı testleri"
Cohesion: 0.07
Nodes (25): successful_payment(), Translator, translate(), MediaStore, job_from_payload(), payload_for(), PaymentService, pack_identity() (+17 more)

### Community 3 - "Görsel işleme ve sansür"
Cohesion: 0.09
Nodes (26): cascade_xml(), censor_regions(), FaceCensor, load_detector(), BoundedBuffer, decode_image(), download_image(), _encode_tile() (+18 more)

### Community 4 - "Ana menü ve gezinme"
Cohesion: 0.16
Nodes (23): fallback(), accept_terms(), cancel(), choose_language(), emoji_command(), emoji_menu(), language_command(), language_menu() (+15 more)

### Community 5 - "Stüdyo yükleme akışı"
Cohesion: 0.18
Nodes (9): receive_image(), select_format(), select_grid(), studio_command(), studio_menu(), Flow, submit(), studio_formats() (+1 more)

### Community 7 - "Şablonlar ve çalışma kilidi"
Cohesion: 0.16
Nodes (5): RuntimeLock, draw_blueprint(), TemplateService, test_blueprint_uses_shared_processing_limit(), test_runtime_lock_excludes_second_process_and_releases()

### Community 8 - "Dil ve ödeme doğrulama"
Cohesion: 0.18
Nodes (3): checkout(), detect_language(), I18nMiddleware

### Community 9 - "Güncelleme ve ödeme kurtarma"
Cohesion: 0.17
Nodes (3): configure_dispatcher(), PrivateFlowMiddleware, DurableDispatcher

## Knowledge Gaps
- **13 isolated node(s):** `telegram-emoji-photo-bot`, `Environment file .env`, `no-new-privileges security option`, `SQLite WAL default storage — implemented`, `Owner-bound checkout validation with 7.5-second DB timeout — implemented` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 109 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Repository` connect `Kota ödeme veritabanı` to `Ürün ve gelir planı`, `Medya teslimatı testleri`, `Bot çalışma bileşenleri`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `Repository` (e.g. with `Atomic quota reservation and job insertion — implemented` and `Database`) actually correct?**
  _`Repository` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `telegram-emoji-photo-bot`, `Environment file .env`, `no-new-privileges security option` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Kota ödeme veritabanı` be split into smaller, more focused modules?**
  _Cohesion score 0.07355242566510173 - nodes in this community are weakly interconnected._
- **Why does `AI Grid Studio — implemented, 1×1–9×9` connect `Ürün ve gelir planı` to `Stüdyo yükleme akışı`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `main()` (e.g. with `.close()` and `.initialize()`) actually correct?**
  _`main()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `Ürün ve gelir planı` be split into smaller, more focused modules?**
  _Cohesion score 0.05687645687645688 - nodes in this community are weakly interconnected._

## Token accounting note

The agent tool does not expose per-agent input/output token counters in this session. Structural AST extraction used no LLM; semantic extraction was performed by a host sub-agent without an external API key. No external LLM charges were incurred by graphify. Host-session token usage is unavailable.

## Graph health warning

159 dangling_endpoint_edges, 75 directed_same_endpoint_collapsed_edges, 75 undirected_same_endpoint_collapsed_edges.
