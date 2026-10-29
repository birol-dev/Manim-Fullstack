"""Quiz question: a question, 2-4 answers, a thinking timer, then the reveal."""

from pydantic import field_validator

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, integer, items, toggle
from studio.schema import text as text_field

META = TemplateMeta(
    id="quiz",
    title="Quiz question",
    summary="A question with 2-4 answers, a thinking timer and the answer reveal.",
    category="teach",
    when_to_use="One multiple-choice or true/false question for class (projector) or social media: "
                "the question and answers appear, a countdown runs while people think, then the correct "
                "answer lights up with an optional explanation. The video length comes from the content "
                "(thinking time + reveal), so there is no length setting.",
    not_for="Several questions in one video: make one video per question. Open questions without answer "
            "choices: use a title or announcement template. A bare timer with no question: use the countdown.",
    default_aspect="16:9",
    min_length=6,
    max_length=60,
    default_length=18,
    length_from_params=True,
    tags=["quiz", "question", "trivia", "classroom", "teacher", "multiple choice", "true or false"],
)


class Option(Item):
    text: str = text_field("", title="Answer", max_length=40, placeholder="Type an answer")

    @field_validator("text")
    @classmethod
    def _filled(cls, value):
        if not value.strip():
            raise ValueError("Write the answer text.")
        return value


class Params(TemplateParams):
    label: str = text_field("Question 1", title="Label", max_length=32,
                            description="A small line above the question, e.g. 'Question 3 of 10'. "
                                        "Leave empty for none.")
    question: str = text_field("Which planet is known as the Red Planet?", title="Question", max_length=120,
                               multiline=True, description="The question. Plain text: write 7 x 8 = ? "
                                                           "instead of formulas.")
    options: list[Option] = items(
        [Option(text="Venus"), Option(text="Mars"), Option(text="Jupiter"), Option(text="Mercury")],
        title="Answers", min_items=2, max_items=4, item_title="Answer",
        description="2 to 4 short answers (use two for true/false). The order you list them is the order shown.")
    correct: int = integer(2, title="Correct answer", ge=1, le=4, choice_of="options",
                           help="Choose the right answer.",
                           description="The position of the correct answer in the list: 1 is the first "
                                       "answer, 2 the second, and so on.")
    think_seconds: int = integer(8, title="Thinking time", ge=3, le=30, unit="seconds",
                                 description="How long the countdown runs before the answer is revealed.")
    explanation: str = text_field("", title="Explanation", max_length=120,
                                  description="Shown after the answer is revealed, e.g. why it is correct. "
                                              "Leave empty for none.")
    show_letters: bool = toggle(True, title="Show A, B, C, D", description="Letter badges next to the answers.")

    @field_validator("options", mode="before")
    @classmethod
    def _plain_answers(cls, value):
        """Agents may pass plain strings: ["Paris", "Rome"]."""
        if isinstance(value, list):
            return [{"text": v} if isinstance(v, str) else v for v in value]
        return value

    @field_validator("question")
    @classmethod
    def _question_filled(cls, value):
        if not value.strip():
            raise ValueError("Write the question.")
        return value

    @field_validator("correct")
    @classmethod
    def _correct_exists(cls, value, info):
        options = info.data.get("options")
        if options is not None and value > len(options):
            raise ValueError(f"There are only {len(options)} answers: choose a number from 1 to {len(options)}.")
        return value


PRESETS = [
    Preset(
        id="general-knowledge", title="General knowledge", summary="A four-answer trivia question with a short explanation.",
        params={
            "label": "Question 3 of 10",
            "question": "Which planet is known as the Red Planet?",
            "options": [{"text": "Venus"}, {"text": "Mars"}, {"text": "Jupiter"}, {"text": "Mercury"}],
            "correct": 2,
            "think_seconds": 8,
            "explanation": "Iron oxide, or rust, on its surface gives Mars its red color.",
        },
        settings={"theme": "midnight"}, tags=["trivia"],
    ),
    Preset(
        id="vocabulary", title="Vocabulary", summary="What does this word mean? Great for language classes.",
        params={
            "label": "Word of the day",
            "question": "What does 'ephemeral' mean?",
            "options": [{"text": "Lasting a very short time"}, {"text": "Extremely large"},
                        {"text": "Related to the weather"}, {"text": "Easy to understand"}],
            "correct": 1,
            "think_seconds": 10,
            "explanation": "From the Greek ephemeros: lasting only a day. Example: ephemeral fashion trends.",
        },
        settings={"theme": "clean"}, tags=["language", "english"],
    ),
    Preset(
        id="classroom-math", title="Classroom math", summary="Mental math for the projector, in plain text.",
        params={
            "label": "Mental math",
            "question": "7 × 8 = ?",
            "options": [{"text": "54"}, {"text": "56"}, {"text": "58"}, {"text": "64"}],
            "correct": 2,
            "think_seconds": 10,
            "explanation": "7 × 8 = 56. Tip: 7 × 4 = 28, then double it.",
        },
        settings={"theme": "chalk"}, tags=["math", "classroom"],
    ),
    Preset(
        id="true-or-false", title="True or false", summary="Two big answers: a fast myth-buster.",
        params={
            "label": "True or false?",
            "question": "Lightning never strikes the same place twice.",
            "options": [{"text": "True"}, {"text": "False"}],
            "correct": 2,
            "think_seconds": 6,
            "explanation": "It happens all the time: the Empire State Building is struck about 20 times a year.",
        },
        settings={"theme": "pop", "energy": "punchy"}, tags=["myth", "social"],
    ),
    Preset(
        id="kids-quiz", title="Kids' quiz", summary="A cheerful animal question with a quick timer.",
        params={
            "label": "Animal quiz",
            "question": "How many legs does a spider have?",
            "options": [{"text": "Six"}, {"text": "Eight"}, {"text": "Ten"}, {"text": "Four"}],
            "correct": 2,
            "think_seconds": 6,
            "explanation": "Spiders have eight legs. Insects only have six!",
        },
        settings={"theme": "pastel", "energy": "punchy"}, tags=["kids", "animals"],
    ),
]
