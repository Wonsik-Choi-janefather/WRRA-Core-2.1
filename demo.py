"""WRRA Core 2.1: finite symbolic allocation and structural inheritance.
Standard library only. Run: python demo.py --output verification.json
This deterministic single-process demonstrator is not a production monitor.
"""
from dataclasses import dataclass, asdict
from fractions import Fraction
import argparse
import hashlib
import json


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class Genotype:
    version: int = 1
    weights: tuple = (60, 40)

    def valid(self):
        return len(self.weights) == 2 and all(type(x) is int and x >= 0 for x in self.weights) and sum(self.weights) > 0

    def identity(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class Proposal:
    revision: int
    kind: str
    envelope: int = 100
    weights: tuple | None = None
    evidence: bool = True
    authorized: bool = True


class Monitor:
    def __init__(self, budget=1000, monitoring=100, genotype=None):
        self.g = genotype or Genotype()
        if not self.g.valid():
            raise ValueError('invalid inherited structure')
        self.budget, self.monitoring = budget, monitoring
        self.reserve, self.revision, self.ledger = 10, 0, []

    def decide(self, p):
        if self.monitoring < 1:
            raise RuntimeError('monitor budget exhausted; no decision executed')
        before_g = self.g.identity()
        before_b, before_m = self.budget, self.monitoring
        self.monitoring -= 1  # fixed declared cost, including rejected proposals
        status, reason, cost, phenotype = 'COMMIT', 'authorized', 0, None
        candidate = self.g
        if p.revision != self.revision:
            status, reason = 'DENY', 'stale_revision'
        elif not p.evidence:
            status, reason = 'OPEN', 'missing_evidence'
        elif not p.authorized:
            status, reason = 'DENY', 'missing_permission'
        elif p.kind not in ('render', 'phenotype', 'genotype'):
            status, reason = 'DENY', 'unknown_action'
        elif type(p.envelope) is not int or p.envelope <= 0:
            status, reason = 'DENY', 'invalid_envelope'
        elif p.kind != 'render' and (p.weights is None or not Genotype(weights=p.weights).valid()):
            status, reason = 'DENY', 'invalid_weights'
        else:
            cost = 2 if p.kind == 'genotype' else p.envelope
            if self.budget - cost < self.reserve:
                status, reason = 'DENY', 'insufficient_resources'
            elif p.kind == 'genotype':
                candidate = Genotype(self.g.version + 1, tuple(p.weights))
            else:
                weights = self.g.weights if p.kind == 'render' else p.weights
                phenotype = tuple(Fraction(p.envelope * w, sum(weights)) for w in weights)
                assert sum(phenotype) == p.envelope
        if status == 'COMMIT':
            self.budget -= cost
            self.g = candidate
        else:
            cost = 0
            assert self.g.identity() == before_g
        self.revision += 1  # every checked proposal changes ledger/resource state
        event = dict(proposal=asdict(p), status=status, reason=reason,
                     Q=int(status == 'COMMIT'), parent_structure=before_g,
                     successor_structure=self.g.identity(), structure_version=self.g.version,
                     phenotype=None if phenotype is None else [str(x) for x in phenotype],
                     action_cost=cost, monitoring_cost=1,
                     budget_before=before_b, budget_after=self.budget,
                     monitoring_before=before_m, monitoring_after=self.monitoring)
        assert before_b - self.budget == cost
        assert before_m - self.monitoring == 1
        assert self.budget >= self.reserve
        self.ledger.append(event)
        return event

    def proposal(self, kind='render', **kwargs):
        return Proposal(self.revision, kind, **kwargs)

    def checkpoint(self):
        data = dict(genotype=asdict(self.g), budget=self.budget, monitoring=self.monitoring,
                    reserve=self.reserve, revision=self.revision, ledger=self.ledger)
        # This serialization models an existing description, not physical cloning.
        return json.dumps(dict(payload=data, sha256=digest(data)), sort_keys=True)

    @classmethod
    def restore(cls, checkpoint):
        wrapped = json.loads(checkpoint)
        data = wrapped['payload']
        if digest(data) != wrapped['sha256']:
            raise ValueError('checkpoint integrity failure')
        raw = data['genotype']
        obj = cls(data['budget'], data['monitoring'], Genotype(raw['version'], tuple(raw['weights'])))
        obj.reserve, obj.revision, obj.ledger = data['reserve'], data['revision'], data['ledger']
        return obj


def verify():
    cases = []
    def record(name, monitor, **extra):
        cases.append(dict(name=name, passed=True, events=monitor.ledger, **extra))

    m = Monitor(); initial = m.g.identity()
    override = m.decide(m.proposal('phenotype', weights=(50, 50)))
    assert override['phenotype'] == ['50', '50'] and m.g.identity() == initial
    normal = m.decide(m.proposal())
    assert normal['phenotype'] == ['60', '40']
    record('one_time_output_override_preserves_structure', m)

    m = Monitor(); m.decide(m.proposal('genotype', weights=(50, 50)))
    assert m.g.version == 2 and m.g.weights == (50, 50)
    normal = m.decide(m.proposal())
    assert normal['phenotype'] == override['phenotype'] and m.g.identity() != initial
    record('amendment_inherited_by_subsequent_execution', m)

    checkpoint = m.checkpoint(); restored = Monitor.restore(checkpoint)
    assert restored.g == m.g and restored.budget == m.budget and restored.monitoring == m.monitoring
    assert restored.decide(restored.proposal())['phenotype'] == ['50', '50']
    damaged = json.loads(checkpoint); damaged['payload']['genotype']['weights'] = [90, 10]
    try:
        Monitor.restore(json.dumps(damaged))
    except ValueError:
        pass
    else:
        raise AssertionError('tampered checkpoint accepted')
    record('reconstruction_and_tamper_rejection', restored)

    m = Monitor(); old = m.g.identity()
    assert m.decide(m.proposal(envelope=80))['phenotype'] == ['48', '32']
    assert m.g.identity() == old
    record('changed_input_changes_phenotype_without_genotype_change', m)

    m = Monitor(); stale = m.proposal('genotype', weights=(50, 50))
    m.decide(m.proposal())
    event = m.decide(stale)
    assert event['reason'] == 'stale_revision' and event['Q'] == 0 and m.g.version == 1
    record('stale_amendment_denied', m)

    for name, kwargs, expected in [
        ('missing_evidence_remains_open', dict(evidence=False), 'OPEN'),
        ('unauthorized_amendment_denied', dict(authorized=False), 'DENY'),
        ('invalid_structure_denied', dict(weights=(-1, 2)), 'DENY')]:
        m = Monitor(); options=dict(weights=(50, 50));options.update(kwargs)
        event=m.decide(m.proposal('genotype', **options))
        assert event['status'] == expected and event['Q'] == 0
        assert event['parent_structure'] == event['successor_structure']
        assert event['action_cost'] == 0 and event['monitoring_cost'] == 1
        record(name, m)

    m = Monitor(budget=100)
    event = m.decide(m.proposal())
    assert event['reason'] == 'insufficient_resources' and event['phenotype'] is None
    assert m.budget == 100 and m.monitoring == 99
    record('reserve_preserving_denial', m)
    assert len(cases) == 9
    return dict(title='WRRA Core 2.1', model='finite symbolic demonstrator',
                assumptions=['trusted single-process monitor', 'declared exact symbolic costs',
                             'no concurrent external mutation', 'checkpoint restores a description'],
                verification={'passed': len(cases), 'total': len(cases)}, cases=cases)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='verification.json')
    args=parser.parse_args();result=verify()
    with open(args.output,'w',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,ensure_ascii=False)
    print(json.dumps(result['verification']))
