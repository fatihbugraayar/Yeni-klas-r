import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cache import save_semantic_cache
from graphify.cluster import cluster, score_all
from graphify.detect import save_manifest
from graphify.diagnostics import diagnose_extraction, format_diagnostic_report
from graphify.export import to_json
from graphify.report import generate

ROOT = Path.cwd()
OUT = ROOT / 'graphify-out'


def read(name, default=None):
    path = OUT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def report(G, communities, cohesion, labels, analysis, extraction, detection):
    questions = suggest_questions(G, communities, labels)
    text = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'],
                    detection, {'input': extraction.get('input_tokens', 0),
                                'output': extraction.get('output_tokens', 0)},
                    str(ROOT), suggested_questions=questions)
    text = text.replace('- Token cost: 0 input · 0 output',
                        '- Token cost: unavailable (host-agent counters are not exposed)')
    text += ('\n\n## Token accounting note\n\n'
             'The agent tool does not expose per-agent input/output token counters in this session. '
             'Structural AST extraction used no LLM; semantic extraction was performed by a '
             'host sub-agent without an external API key. No external LLM charges were incurred '
             'by graphify. Host-session token usage is unavailable.\n')
    health = read('graph_health.json', {})
    flags = {key: health.get(key, 0) for key in (
        'dangling_endpoint_edges', 'missing_endpoint_edges', 'self_loop_edges',
        'directed_same_endpoint_collapsed_edges', 'undirected_same_endpoint_collapsed_edges'
    ) if health.get(key, 0)}
    if flags:
        text += '\n## Graph health warning\n\n' + ', '.join(f'{v} {k}' for k, v in flags.items()) + '.\n'
    (OUT / 'GRAPH_REPORT.md').write_text(text, encoding='utf-8')
    return questions


def build():
    chunks = sorted(OUT.glob('.graphify_chunk_*.json'))
    if not chunks:
        raise SystemExit('Semantic chunk missing; build aborted')
    new = {'nodes': [], 'edges': [], 'hyperedges': [], 'input_tokens': 0, 'output_tokens': 0,
           'token_usage_status': 'unavailable'}
    for path in chunks:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data.get('nodes'), list) or not isinstance(data.get('edges'), list):
            raise SystemExit(f'Invalid chunk: {path.name}')
        for kind in ('nodes', 'edges', 'hyperedges'):
            new[kind].extend(data.get(kind, []))
    save_semantic_cache(new['nodes'], new['edges'], new['hyperedges'], root=str(ROOT))
    cached = read('.graphify_cached.json', {'nodes': [], 'edges': [], 'hyperedges': []})
    semantic = dict(new)
    semantic['nodes'] = list({n['id']: n for n in cached['nodes'] + new['nodes']}.values())
    for kind in ('edges', 'hyperedges'):
        semantic[kind] = cached.get(kind, []) + new[kind]
    write('.graphify_semantic.json', semantic)
    ast = read('.graphify_ast.json')
    seen = {n['id'] for n in ast['nodes']}
    extraction = {**semantic, 'nodes': ast['nodes'] + [n for n in semantic['nodes'] if n['id'] not in seen],
                  'edges': ast['edges'] + semantic['edges']}
    write('.graphify_extract.json', extraction)
    G = build_from_json(extraction, root=str(ROOT), directed=False)
    if G.number_of_nodes() == 0:
        raise SystemExit('Graph is empty; no outputs written')
    communities = cluster(G)
    cohesion = score_all(G, communities)
    analysis = {'communities': {str(k): v for k, v in communities.items()},
                'cohesion': {str(k): v for k, v in cohesion.items()},
                'gods': god_nodes(G), 'surprises': surprising_connections(G, communities)}
    if not to_json(G, communities, str(OUT / 'graph.json')):
        raise SystemExit('Graph shrink guard prevented export')
    diagnostic = diagnose_extraction(extraction, directed=False, root=str(ROOT))
    write('graph_health.json', diagnostic)
    (OUT / 'GRAPH_HEALTH.md').write_text(format_diagnostic_report(diagnostic), encoding='utf-8')
    labels = {cid: 'Community ' + str(cid) for cid in communities}
    analysis['questions'] = report(G, communities, cohesion, labels, analysis, extraction,
                                   read('.graphify_detect.json'))
    write('.graphify_analysis.json', analysis)
    print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
    print(format_diagnostic_report(diagnostic))
    for cid, ids in communities.items():
        ordered = sorted(ids, key=lambda node: G.degree(node), reverse=True)
        files = Counter(G.nodes[node].get('source_file', '') for node in ids)
        print(json.dumps({'community': cid, 'cohesion': cohesion[cid],
                          'size': len(ids), 'files': files.most_common(3),
                          'labels': [G.nodes[node].get('label', node) for node in ordered[:14]]},
                         ensure_ascii=False))


def label():
    extraction = read('.graphify_extract.json')
    G = build_from_json(extraction, root=str(ROOT), directed=False)
    analysis = read('.graphify_analysis.json')
    communities = {int(k): v for k, v in analysis['communities'].items()}
    cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
    labels = {int(k): v for k, v in read('.graphify_labels.json').items()}
    report(G, communities, cohesion, labels, analysis, extraction, read('.graphify_detect.json'))
    print('Report updated with community labels')


def finish():
    detection = read('.graphify_detect.json')
    save_manifest(detection.get('all_files') or detection['files'], root=str(ROOT))
    cost = read('cost.json', {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0})
    cost['runs'].append({'date': datetime.now(timezone.utc).isoformat(), 'input_tokens': None,
                        'output_tokens': None, 'files': detection['total_files'],
                        'token_usage_status': 'unavailable', 'external_llm_api_calls': 0})
    cost['token_usage_status'] = 'unavailable'
    cost['total_input_tokens'] = None
    cost['total_output_tokens'] = None
    write('cost.json', cost)
    for pattern in ('.graphify_chunk_*.json', '.graphify_detect.json', '.graphify_extract.json',
                    '.graphify_ast.json', '.graphify_semantic.json', '.graphify_analysis.json',
                    '.graphify_cached.json', '.graphify_uncached.txt', '.needs_update'):
        for path in OUT.glob(pattern):
            path.unlink(missing_ok=True)
    print('Manifest saved. Semantic token counts unavailable; no external LLM API calls.')


if __name__ == '__main__':
    {'build': build, 'label': label, 'finish': finish}[sys.argv[1]]()
