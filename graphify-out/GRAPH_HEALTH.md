[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 367
unverified_code_nodes: 0
raw_edges: 1152
valid_candidate_edges: 993
missing_endpoint_edges: 0
dangling_endpoint_edges: 159
external_reference_edges: 0
self_loop_edges: 0
exact_duplicate_edges: 0
directed_unique_endpoint_pairs: 918
directed_same_endpoint_collapsed_edges: 75
undirected_unique_endpoint_pairs: 918
undirected_same_endpoint_collapsed_edges: 75
same_endpoint_group_count: 74
relation_variant_groups: 55
source_file_variant_groups: 0
source_location_variant_groups: 16
context_variant_groups: 18
post_build_graph_type: Graph
post_build_edges: 1069
producer_suppression_sites: 12
producer_suppression_examples:
  - L1749 seen_ids arity=unknown
  - L2282 seen_ids arity=unknown
  - L2284 seen_doc_refs arity=unknown
  - L2762 seen_ids arity=unknown
  - L2909 seen_ids arity=unknown
  - L3743 seen_keys arity=unknown
  - L3916 seen_keys arity=unknown
  - L6273 seen_ids arity=unknown
examples:
  - telegram_bot_handlers_ai_studio_handlers_receive_image -> telegram_bot_handlers_ai_studio_handlers_py_message edges=3 relations=['references'] locations=['L47', 'L48', 'L49'] contexts=['decorator', 'parameter_type']
  - telegram_bot_database_repository_repository_create_job -> telegram_bot_database_models_job edges=2 relations=['references'] locations=['L66'] contexts=['parameter_type', 'return_type']
  - telegram_bot_database_repository_repository_create_job_49c716 -> telegram_bot_database_models_job edges=2 relations=['references'] locations=['L76'] contexts=['parameter_type', 'return_type']
  - telegram_bot_handlers_ai_studio_handlers_studio_command -> telegram_bot_handlers_ai_studio_handlers_py_message edges=2 relations=['references'] locations=['L16', 'L17'] contexts=['decorator', 'parameter_type']
  - telegram_bot_handlers_emoji_handlers_upload_emoji -> telegram_bot_handlers_emoji_handlers_py_message edges=2 relations=['references'] locations=['L20', 'L21'] contexts=['decorator', 'parameter_type']
note: normal graph.json is post-build; raw producer loss must be measured earlier.