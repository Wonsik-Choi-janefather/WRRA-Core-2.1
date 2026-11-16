"""Check the packed state width for a finite, one-job timing model."""
import json

WAIT, GRACE, CONFIRM_ONSET = 5000, 4000, 140
DRAFTS = 40

waiting_range = range(1, WAIT + CONFIRM_ONSET + 1)
decoding_range = range(1, WAIT + GRACE - CONFIRM_ONSET + 1)
assert len(waiting_range) + len(decoding_range) == 2 * WAIT + GRACE
assert WAIT - 1 + CONFIRM_ONSET < len(waiting_range) <= WAIT + CONFIRM_ONSET


def states(labels):
    one = DRAFTS * 2 * (len(waiting_range) + len(decoding_range)) * labels + DRAFTS + 1
    two = one**2 + DRAFTS**2
    return one, (one - 1).bit_length(), two, (two - 1).bit_length()


assert states(1)[1::2] == (21, 41)
assert states(2)[1::2] == (22, 43)
print(json.dumps({"waiting": len(waiting_range), "decoding": len(decoding_range),
                  "states_and_bits_1_label": states(1), "states_and_bits_2_labels": states(2)}, indent=2))
