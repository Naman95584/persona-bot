"""engine._trim: cut chatty replies to the sentence limit, but never lose the final question."""
from persona_bot.live.engine import new_call
from persona_bot.sarvam.client import MockClient

S1, S2, S3 = "समझ गई sir।", "आपका time valuable है।", "हमारा advisor बस 15 minute लेगा।"
Q = "आज शाम या कल सुबह, कौन सा slot ठीक रहेगा?"
LONG = f"{S1} {S2} {S3} {Q} धन्यवाद।"


def _trim(seller_id, text):
    return new_call(seller_id, client=MockClient())._trim(text)


def test_crisp_is_acknowledgement_plus_question():
    assert _trim("R001", LONG) == f"{S1} {Q}"                    # R001 is crisp; trailing "धन्यवाद" dropped


def test_normal_is_two_sentences_ending_on_the_question():
    assert _trim("R008", LONG) == f"{S1} {Q}"                    # R008 is normal (limit 2)


def test_explanatory_gets_three_sentences_ending_on_the_question():
    assert _trim("R004", LONG) == f"{S1} {S2} {Q}"               # R004 is explanatory (limit 3)


def test_without_a_question_the_sentence_limit_still_applies():
    assert _trim("R001", f"{S1} {S2} {S3}") == S1


def test_short_replies_are_untouched():
    assert _trim("R001", f"{S2} कल सुबह?") == f"{S2} कल सुबह?"


def test_a_reply_that_is_only_a_question_is_kept():
    assert _trim("R001", f"{S1} {S2} {S3} कल सुबह?") == f"{S1} कल सुबह?"
