"""Quote & text post: quotes, testimonials, hot takes and team values, revealed at reading pace."""

from typing import Literal, Optional

from studio.schema import HexColor, Preset, TemplateMeta, TemplateParams, choice, color, image, integer, toggle
from studio.schema import text as text_field

META = TemplateMeta(
    id="quote",
    title="Quote & text post",
    summary="Quotes, customer reviews and hot takes that appear at reading pace.",
    category="creator",
    when_to_use="A piece of text that is the whole point: an inspirational or book quote, a customer "
                "testimonial (optionally with a photo and a star rating), an opinion or 'hot take' text post, "
                "a team value or motto. Highlight key words with *asterisks*. The video is as long as the text "
                "needs to be read (never shorter than the length setting).",
    not_for="Several different quotes in a row (make one video per quote). Announcements with a date and place: "
            "use an announcement template. Long articles: this fits about 240 characters.",
    default_aspect="9:16",
    min_length=4,
    max_length=60,
    default_length=8,
    tags=["quote", "testimonial", "review", "text post", "hot take", "motto", "social"],
)


class Params(TemplateParams):
    kicker: str = text_field(
        "", title="Small heading", max_length=40,
        description="An optional short line above the text, e.g. 'Unpopular opinion' or 'What our customers say'. "
                    "Leave empty for none.")
    text: str = text_field(
        "It is not that we have a short time to live, but that we *waste a lot of it*.",
        title="Text", max_length=240, multiline=True,
        description="The quote, review or opinion (up to 240 characters). Put *asterisks* around the words you "
                    "want highlighted in the accent color, e.g. 'Make it *simple*'.")
    author: str = text_field("", title="Name", max_length=40,
                             description="Who said it. Leave empty for none.")
    role: str = text_field("", title="Role or handle", max_length=50,
                           description="A line under the name, e.g. 'Owner, Moda Café' or '@handle'. "
                                       "Leave empty for none.")
    avatar: Optional[str] = image(title="Photo", shape="circle",
                                  description="A photo of the person, shown as a circle next to the name.")
    initials: bool = toggle(False, title="Show initials when there is no photo",
                            description="Draws a colored circle with the person's initials instead of a photo.")
    stars: int = integer(0, title="Star rating", ge=0, le=5,
                         description="0 hides the stars; 1 to 5 draws that many filled stars out of five.")
    reveal: Literal["words", "lines", "sweep"] = choice(
        "words", title="Reveal",
        labels={"words": "Word by word", "lines": "Line by line", "sweep": "Highlight sweep"},
        description="words: each word appears in turn; lines: one line at a time; sweep: all the text is "
                    "shown faded and a highlight reads through it.")
    quote_marks: bool = toggle(True, title="Big quote mark", description="A large decorative quote mark above the text.")
    align: Literal["center", "left"] = choice("center", title="Alignment", labels={"center": "Centered", "left": "Left"})
    accent: HexColor = color(None, title="Highlight color",
                             description="Color of the highlighted words, quote mark and details. Empty = the theme's.")


PRESETS = [
    Preset(
        id="inspirational-quote", title="Inspirational quote",
        summary="A short quote with a big quote mark, revealed word by word.",
        params={"text": "It is not that we have a short time to live, but that we *waste a lot of it*.",
                "author": "Seneca", "role": "On the Shortness of Life", "quote_marks": True,
                "reveal": "words", "align": "center"},
        settings={"theme": "midnight", "energy": "calm"}),
    Preset(
        id="customer-review", title="5-star customer review",
        summary="A testimonial with star rating, name and photo slot.",
        params={"kicker": "What our customers say", "stars": 5,
                "text": "*Best coffee in town.* The team remembers my order, the pastries are always warm, "
                        "and I've stopped brewing at home.",
                "author": "Elif Demir", "role": "Regular at Moda Café", "initials": True,
                "quote_marks": False, "reveal": "lines", "align": "center"},
        settings={"theme": "clean"}),
    Preset(
        id="hot-take", title="Hot take",
        summary="A bold opinion post with a handle, left aligned.",
        params={"kicker": "Unpopular opinion",
                "text": "Most meetings should be a *two-line message*. Protect your *focus*.",
                "author": "Maya Torres", "role": "@mayaworks", "initials": True,
                "quote_marks": False, "reveal": "words", "align": "left"},
        settings={"theme": "pop", "energy": "punchy"}),
    Preset(
        id="book-quote", title="Book quote",
        summary="A line from a book with the title as the source.",
        params={"text": "It is not down in any map; *true places* never are.",
                "author": "Herman Melville", "role": "Moby-Dick, 1851", "quote_marks": True,
                "reveal": "sweep", "align": "left"},
        settings={"theme": "newsroom"}),
    Preset(
        id="team-value", title="Team value",
        summary="A motto or value for your team, centered and calm.",
        params={"kicker": "Our values",
                "text": "We *listen first*, then we build. Every customer helps write what we make next.",
                "author": "The Moda Café team", "quote_marks": False, "reveal": "lines", "align": "center"},
        settings={"theme": "pastel", "energy": "calm"}),
]
