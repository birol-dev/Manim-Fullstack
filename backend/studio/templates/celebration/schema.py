"""Celebration card: a warm, animated greeting with a name, an optional count-up number and confetti."""

from typing import Literal, Optional

from studio.schema import (
    HexColor,
    Preset,
    TemplateMeta,
    TemplateParams,
    choice,
    color,
    icon,
    image,
    integer,
    text,
    toggle,
)

META = TemplateMeta(
    id="celebration",
    title="Celebration card",
    summary="Birthdays, anniversaries, milestones, thank-yous and welcomes, with a name, a photo and confetti.",
    category="celebrate",
    when_to_use="A short greeting video to send or post: happy birthday to someone, a work anniversary, a "
                "follower or sales milestone (the number counts up), a thank-you to customers or a team, or "
                "welcoming a new teammate. Optional round photo, optional big number, optional message and "
                "signature. About 7 seconds.",
    not_for="Announcing an event with a date and place: use an announcement template. A countdown to a date: "
            "use the countdown timer. Long messages: keep the message under about 140 characters.",
    default_aspect="9:16",
    min_length=4,
    max_length=30,
    default_length=7,
    tags=["birthday", "anniversary", "milestone", "thank you", "welcome", "congratulations", "confetti", "greeting"],
)

# What each occasion supplies when the form leaves it blank: the greeting and the icon.
# (The scene also uses it to pick a motion flavor.)
OCCASIONS = {
    "birthday": {"headline": "Happy birthday", "icon": "cake"},
    "anniversary": {"headline": "Happy anniversary", "icon": "award"},
    "milestone": {"headline": "We did it!", "icon": "trophy"},
    "thanks": {"headline": "Thank you", "icon": "heart"},
    "welcome": {"headline": "Welcome to the team", "icon": "handshake"},
}


class Params(TemplateParams):
    occasion: Literal["birthday", "anniversary", "milestone", "thanks", "welcome"] = choice(
        "birthday", title="Occasion",
        labels={"birthday": "Birthday", "anniversary": "Anniversary", "milestone": "Milestone",
                "thanks": "Thank you", "welcome": "Welcome"},
        help="Sets the greeting, icon and animation.",
        option_help={"birthday": "A birthday greeting with a cake and confetti.",
                     "anniversary": "An award and a count-up for years together.",
                     "milestone": "A trophy and a big count-up for your achievement.",
                     "thanks": "A warm thank-you with a heart and falling confetti.",
                     "welcome": "A friendly welcome with confetti cannons."},
        description="Sets the default icon and the feel of the animation. An empty headline uses the "
                    "occasion's greeting (Happy birthday, Happy anniversary, We did it!, Thank you, "
                    "Welcome to the team).")
    headline: str = text("Happy birthday", title="Headline", max_length=40,
                         help="Your greeting. Leave empty to use the occasion's greeting.",
                         description="The greeting. Wrap a word in *asterisks* to color it. Leave empty to use "
                                     "the occasion's standard greeting.")
    name: str = text("Sam", title="Name", max_length=30,
                     description="The person, team or milestone this is for. Shown large.")
    number: Optional[int] = integer(None, title="Number", ge=0, le=999_999_999,
                                    help="A number that counts up. Leave empty to hide it.",
                                    description="Optional big number that counts up, e.g. 30 for a 30th "
                                                "birthday, 5 for years, 10000 for followers. Leave empty for none.")
    number_label: str = text("", title="Number label", max_length=30,
                             description="Small text under the number, e.g. 'followers' or 'years at Acme'.")
    compact: bool = toggle(False, title="Short number (10K)",
                           description="Write 10,000 as 10K and 2,500,000 as 2.5M.")
    message: str = text("", title="Message", max_length=140, multiline=True,
                        description="A short personal note under the name. Leave empty for none.")
    photo: Optional[str] = image(title="Photo", shape="circle", crop="circle",
                                 help="A round photo of the person. Leave empty to show an icon.",
                                 description="Optional photo of the person, shown in a circle (cropped to the "
                                             "center). Without a photo an icon is shown instead.")
    from_line: str = text("", title="Signed by", max_length=40,
                          description="Who it is from, e.g. 'With love, the team'. Leave empty for none.")
    confetti: bool = toggle(True, title="Confetti")
    icon: Optional[str] = icon(None, title="Icon",
                               help="Choose an icon, or use the occasion's icon.",
                               description="Name of a bundled icon, e.g. 'cake', 'gift', 'heart', 'star', "
                                           "'trophy'. Leave empty to use the occasion's icon.")
    accent: HexColor = color(None, title="Accent color")


PRESETS = [
    Preset(id="happy-birthday", title="Happy birthday",
           summary="Birthday wishes for one person, with confetti cannons.",
           params={"occasion": "birthday", "headline": "Happy birthday", "name": "Elif",
                   "message": "Wishing you a day full of cake, laughter and everyone you love.",
                   "from_line": "With love, your friends", "confetti": True},
           settings={"theme": "pastel", "aspect": "9:16"}, tags=["birthday"]),
]
