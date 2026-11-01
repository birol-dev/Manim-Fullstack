"""Announcement: one bold message with its details: sales, events, openings, hiring, launches."""

from typing import Literal, Optional

from studio.schema import HexColor, Item, Preset, TemplateMeta, TemplateParams, choice, color, icon, items, text
from studio.schema import image as image_field

META = TemplateMeta(
    id="announcement",
    title="Announcement",
    summary="Say it loud: a sale, an event, an opening, a job or a launch, with the details.",
    category="announce",
    when_to_use="Announcing one thing with a few details: a sale or discount, an event invitation, "
                "opening or holiday hours, a closed notice, a job opening, a launch or a new product. "
                "Kicker, headline, an optional huge element (\"30% OFF\", \"14.06\", \"OPEN\"), up to 4 "
                "detail lines with icons, a call to action and an optional QR code.",
    not_for="Several products with prices (a menu or price-list template), a countdown that runs in real "
            "time (countdown), a long text or a list of more than 4 points.",
    default_aspect="9:16",
    min_length=4,
    max_length=30,
    default_length=8,
    tags=["announcement", "sale", "event", "invite", "opening", "closed", "hiring", "launch", "promo", "qr"],
)


class Detail(Item):
    text: str = text("", title="Text", max_length=32, placeholder="Sat 14 June, 7 pm")
    icon: Optional[str] = icon(None, title="Icon", description="Optional icon, e.g. calendar, clock, map-pin, tag.")


LAYOUTS = {
    "bold": "Bold type",
    "split": "Photo + text",
    "poster": "Ticket card",
}


class Params(TemplateParams):
    layout: Literal["bold", "split", "poster"] = choice(
        "bold", title="Layout", labels=LAYOUTS,
        option_help={"bold": "Big centered words with the big text on a color band.",
                     "split": "Your photo beside the words, or a color panel without a photo.",
                     "poster": "A ticket card with the big text on the stub."},
        description="Bold type: big centered words, the big text on a color band. Photo + text: your photo "
                    "(or a color panel) beside the words. Ticket card: a ticket with the big text on the stub.")
    teaser: str = text("", title="Teaser (optional)", max_length=40, placeholder="Something new is coming…",
                       help="An opening line before the reveal. Leave empty to skip it.",
                       description="Shown on its own first, then the announcement is revealed. Leave empty to "
                                   "start with the announcement.")
    kicker: str = text("This weekend only", title="Top line", max_length=28,
                       description="A short line above the headline, e.g. 'You're invited'.")
    headline: str = text("Summer *sale* on everything", title="Headline", max_length=40,
                         description="The main message. Wrap a word in *asterisks* to color it.")
    big_text: str = text("30% off", title="Big text", max_length=12,
                         description="Optional huge element: a discount, a date, a word (30% OFF, 14.06, OPEN).")
    details: list[Detail] = items(
        [Detail(text="Fri to Sun, 14 to 16 June", icon="calendar"),
         Detail(text="In store and online", icon="store")],
        title="Details", min_items=0, max_items=4, item_title="Detail",
        description="Up to 4 short lines (when, where, price, phone), each with an optional icon.")
    call_to_action: str = text("Show this video at checkout", title="Call to action", max_length=40,
                               description="What people should do, e.g. 'Scan to RSVP'.")
    qr_text: str = text("", title="QR code link", max_length=150, placeholder="https://…",
                        description="A link or text to show as a QR code. Leave empty for no QR code.")
    image: Optional[str] = image_field(title="Photo", crop="free", description="Optional photo or product shot (Photo + text "
                                                                  "layout shows it largest).")
    logo: Optional[str] = image_field(title="Logo", shape="logo", crop="free", description="Optional logo, shown small in a corner.")
    accent: HexColor = color(None, title="Accent color")


PRESETS = [
    Preset(
        id="weekend-sale", title="Weekend sale", summary="30% off, loud and clear, for stories and the shop TV.",
        params={
            "layout": "bold",
            "kicker": "This weekend only",
            "headline": "Summer *sale* on everything",
            "big_text": "30% off",
            "details": [
                {"text": "Fri to Sun, 14 to 16 June", "icon": "calendar"},
                {"text": "In store and online", "icon": "shopping-bag"},
                {"text": "No code needed", "icon": "tag"},
            ],
            "call_to_action": "Show this video at checkout",
        },
        settings={"theme": "pop", "energy": "punchy"},
        tags=["sale", "discount", "shop"],
    ),
    Preset(
        id="event-invite", title="Event invite", summary="Date, time and place on a ticket, with a QR to RSVP.",
        params={
            "layout": "poster",
            "kicker": "You're invited",
            "headline": "Rooftop *summer* party",
            "big_text": "14.06",
            "details": [
                {"text": "Saturday, 14 June", "icon": "calendar"},
                {"text": "From 7 pm until late", "icon": "clock"},
                {"text": "Terrace Bar, 5th floor", "icon": "map-pin"},
                {"text": "Free entry, bring a friend", "icon": "ticket"},
            ],
            "call_to_action": "Scan to RSVP by 10 June",
            "qr_text": "https://example.com/rsvp",
        },
        settings={"theme": "pastel"},
        tags=["event", "party", "invite", "meetup"],
    ),
]
