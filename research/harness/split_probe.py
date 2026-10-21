"""Where the merged-token split fires on synthetic noise, and what it does there."""
import sys, random, collections
sys.path.insert(0, "engine")
from haanji.bench import corpus_of, entity_errors
from haanji.corrupt import corrupt
from haanji.bhasha.bridge import BhashaBridge
from haanji.bhasha.lexicon import TenantLexicon
from haanji.config import BhashaConfig
from haanji.models import Token, Transcript
from haanji.vertical import list_packs, load_pack

packs = [load_pack(n) for n in list_packs()]
rate = 0.30
fired = 0; worse = 0; better = 0; same = 0
shown = 0
for pack in packs:
    index = pack.entity_index()
    lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
    br = BhashaBridge(lex, BhashaConfig(enabled=True))
    br_nosplit = BhashaBridge(lex, BhashaConfig(enabled=True)); br_nosplit.MIN_MERGED_LEN = 10**6
    rng = random.Random(4242 + 30)
    for truth in corpus_of(pack):
        for _ in range(12):
            heard, low = corrupt(truth, rate, rng)
            low_set = {w.lower() for w in low}
            toks = [Token(w, 0.42 if w.lower() in low_set else 0.94) for w in heard.split()]
            a = br.correct(Transcript(toks, True)); b = br_nosplit.correct(Transcript(toks, True))
            if any(" " in c.to_surface and c.entry_weight == 0.0 for c in a.corrections):
                fired += 1
                _, ea = entity_errors(truth, a.text, index); _, eb = entity_errors(truth, b.text, index)
                if ea > eb: worse += 1
                elif ea < eb: better += 1
                else: same += 1
                if ea > eb and shown < 12:
                    shown += 1
                    print(f"TRUTH {truth}\n  heard {heard}\n  split {a.text}\n  plain {b.text}")
print(f"split fired on {fired} sentences: worse {worse}, better {better}, same {same}")
