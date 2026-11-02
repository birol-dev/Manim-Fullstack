"""Quiz: one question, or a whole quiz of up to 12, each with answers and a thinking timer."""

from pydantic import field_validator

from studio.schema import Item, Preset, TemplateMeta, TemplateParams, integer, items, toggle
from studio.schema import text as text_field

META = TemplateMeta(
    id="quiz",
    title="Quiz",
    summary="Questions with 2-4 answers, a thinking timer and the answer reveal: one, or a whole quiz.",
    category="teach",
    when_to_use="A multiple-choice or true/false question for class (projector) or social media, or a quiz "
                "of up to 12 questions in one video: each question and answers appear, a countdown runs "
                "while people think, then the correct answer lights up with an optional explanation, and "
                "the next question follows. The video length comes from the content (questions x thinking "
                "time + reveals), so there is no length setting.",
    not_for="Open questions without answer choices: use a title or announcement template. A bare timer "
            "with no question: use the countdown. More than 12 questions: split them into two videos.",
    default_aspect="16:9",
    min_length=6,
    max_length=540,
    default_length=18,
    length_from_params=True,
    tags=["quiz", "questions", "trivia", "classroom", "teacher", "multiple choice", "true or false"],
)


class Option(Item):
    text: str = text_field("", title="Answer", max_length=40, placeholder="Type an answer")

    @field_validator("text")
    @classmethod
    def _filled(cls, value):
        if not value.strip():
            raise ValueError("Write the answer text.")
        return value


class Question(Item):
    """A further question; the first question keeps the original top-level fields."""

    question: str = text_field("", title="Question", max_length=120, multiline=True,
                               description="The question. Plain text: write 7 x 8 = ? instead of formulas.")
    options: list[Option] = items(
        [{"text": ""}, {"text": ""}],
        title="Answers", min_items=2, max_items=4, item_title="Answer",
        description="2 to 4 short answers (use two for true/false). The order you list them is the order shown.")
    correct: int = integer(1, title="Correct answer", ge=1, le=4, choice_of="options",
                           help="Choose the right answer.",
                           description="The position of the correct answer in the list: 1 is the first "
                                       "answer, 2 the second, and so on.")
    explanation: str = text_field("", title="Explanation", max_length=120,
                                  description="Shown after the answer is revealed, e.g. why it is correct. "
                                              "Leave empty for none.")

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


MAX_QUESTIONS = 12


def label_for(index: int, total: int, typed: str) -> str:
    """The line above a question: the typed label alone, or a self-counting one in a quiz."""
    return typed if total <= 1 else f"Question {index} of {total}"


class Params(TemplateParams):
    label: str = text_field("Question 1", title="Label", max_length=32,
                            description="A small line above the question, e.g. 'Question 3 of 10'. "
                                        "With more than one question the count fills in by itself; "
                                        "leave empty for none.",
                            help="A line above the question, or leave empty.")
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
    explanation: str = text_field("", title="Explanation", max_length=120,
                                  description="Shown after the answer is revealed, e.g. why it is correct. "
                                              "Leave empty for none.")
    questions: list[Question] = items(
        [], title="More questions", min_items=0, max_items=MAX_QUESTIONS - 1, item_title="Question",
        description="Add up to 11 more questions for one video (12 in all). Each one appears after the "
                    "first, with the same thinking time and look.",
        help="Add more questions: 12 in one video at most.")
    think_seconds: int = integer(8, title="Thinking time", ge=3, le=30, unit="seconds",
                                 description="How long the countdown runs before each answer is revealed.")
    show_letters: bool = toggle(True, title="Show A, B, C, D", description="Letter badges next to the answers.")

    @field_validator("questions", mode="before")
    @classmethod
    def _questions_limit(cls, value):
        if isinstance(value, list) and len(value) > MAX_QUESTIONS - 1:
            raise ValueError(f"A video can hold up to {MAX_QUESTIONS} questions. "
                             "Put the rest in another video.")
        return value

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
    Preset(
        id="five-question-quiz", title="Five-question class quiz",
        summary="Five general knowledge questions with answers and short explanations, in one video.",
        params={
            "label": "",
            "question": "Which planet is known as the Red Planet?",
            "options": [{"text": "Venus"}, {"text": "Mars"}, {"text": "Jupiter"}, {"text": "Mercury"}],
            "correct": 2,
            "explanation": "Iron oxide, or rust, on its surface gives Mars its red color.",
            "questions": [
                {
                    "question": "What is the largest ocean on Earth?",
                    "options": [{"text": "Atlantic"}, {"text": "Indian"}, {"text": "Pacific"}, {"text": "Arctic"}],
                    "correct": 3,
                    "explanation": "The Pacific covers about a third of Earth, more than all the land together.",
                },
                {
                    "question": "How many sides does a hexagon have?",
                    "options": [{"text": "Five"}, {"text": "Six"}, {"text": "Seven"}, {"text": "Eight"}],
                    "correct": 2,
                    "explanation": "Hexa means six. A honeycomb cell is a hexagon.",
                },
                {
                    "question": "Which gas do plants take in from the air to make food?",
                    "options": [{"text": "Oxygen"}, {"text": "Nitrogen"}, {"text": "Carbon dioxide"},
                                {"text": "Hydrogen"}],
                    "correct": 3,
                    "explanation": "Plants use sunlight, water and carbon dioxide, and give out oxygen.",
                },
                {
                    "question": "Who painted the Mona Lisa?",
                    "options": [{"text": "Vincent van Gogh"}, {"text": "Leonardo da Vinci"},
                                {"text": "Claude Monet"}, {"text": "Pablo Picasso"}],
                    "correct": 2,
                    "explanation": "Da Vinci painted it in the early 1500s. It hangs in the Louvre, Paris.",
                },
            ],
            "think_seconds": 10,
        },
        settings={"theme": "midnight"}, tags=["quiz", "classroom", "general knowledge", "trivia", "teacher"],
    ),
]
