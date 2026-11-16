from itertools import product

encodings = set()
for outer, first, second in product(range(4), range(16), range(16)):
    state = 256 * outer + 16 * first + second
    decoded = (state // 256, (state // 16) % 16, state % 16)
    assert decoded == (outer, first, second)
    encodings.add(state)
assert len(encodings) == 1024
assert len({state & 511 for state in encodings}) == 512
print("1,024 states verified. Exact fixed-width lower bound: 10 bits.")
