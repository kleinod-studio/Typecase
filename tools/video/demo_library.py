"""The sample library of the explainer videos: "The Lighthouse Keeper", a short novel in the
making, in English or German. All text is made up for it (the story is also used for the
screenshots of Endpaper). Every video starts from the same library, so it always looks familiar.

    build(folder, "en")  # or "de"

Icons and colors are left at the standard; a video that wants them sets them itself
(see LOOKS). build(folder, "en", extras=True) adds what the tour of the app shows: an empty
chapter to write in, the start of a thesis and a letter (English only)."""

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

# What build(..., extras=True) adds (the tour video, English only)
EXTRAS = {
    "chapter": ("07 The Light", "The Light", "Chapter 7"),
    "thesis": ("Thesis", "1 Introduction", (
        "# 1 Introduction\n\n"
        "Lighthouses have guided ships along dangerous coasts for more than two thousand years.^[The Pharos of "
        "Alexandria, finished around 280 BC, is the earliest one we know of.] This thesis looks at how their "
        "keepers lived and worked between 1850 and 1950, when the last towers on the coast were still lit by hand.\n\n"
        "## 1.1 Research question\n\n"
        "How did the routine of the light shape the lives of the people who kept it?\n\n"
        "## 1.2 Sources\n\n"
        "- Keepers' logs from twelve stations\n"
        "- Letters to and from the mainland\n"
        "- Interviews with the families of former keepers\n"
    )),
    "letter": ("Letters", "Dear Mira", (
        "Skerry Island, 3 November\n\n"
        "Dear Mira,\n\n"
        "The boat came at last, and with it your parcel. The tea is *wonderful*, and the socks are already on my feet.\n\n"
        "The nights are long now. I light the lamp at a quarter to five, and some evenings I sit up there until the "
        "first ship goes by, just to watch it change course.\n\n"
        "Write soon, and tell me everything.\n\n"
        "With love,  \nAda\n"
    )),
}

# name in English: (icon, color), as set in the icons-and-colors video
LOOKS = {
    "The Lighthouse Keeper": ("book", "purple"),
    "Characters": ("person", "teal"),
    "Places": ("place", "green"),
    "Ideas": ("idea", "yellow"),
    "02 The Storm": ("star", "orange"),
}

TEXT = {
    "en": {
        "library": "Writing",
        "novel": "The Lighthouse Keeper",
        "manuscript": "Manuscript",
        "characters": "Characters",
        "places": "Places",
        "notes": "Notes",
        "ideas": "Ideas",
        "questions": "Open Questions",
        "author": "Ada Morrow",
        "draft": "Draft",
        "revised": "Revised",
        "chapter": "Chapter",
        "caption": "The tower on the evening of the storm",
        "alt": "A red and white lighthouse on a dark island at dusk. Its light sweeps across a cloudy sky, "
        "and a small sailing boat lies on the sea.",
        "link": "https://en.wikipedia.org/wiki/Beaufort_scale",
        "chapters": [
            ("01 Arrival", "Arrival", 250, [
                "The boat left Ada on the jetty with two crates, a sack of flour and a letter she was not to open "
                "until the first of the month. The boatman did not wait to see her climb the path. He had his own "
                "weather to think about, and the island was not a place where people lingered.",
                "The lighthouse stood at the top of the rise, white against a sky that could not decide between "
                "rain and sun. From below it looked smaller than it had in the drawings her father kept above his "
                "desk, and older, as if the wind had been sanding it for a hundred years. It had.",
                "Inside, the keeper's room smelled of paraffin and salt. A kettle sat on the stove, cold. On the "
                "table lay the log, open at the last entry: *Wind west, moderate. Lamp lit at 5.40. All well.* "
                "The handwriting was her father's.",
            ]),
            ("02 The Storm", "The Storm", 250, [
                "The barometer had been falling since noon. Ada tapped the glass twice, the way her father used "
                "to,^[He called it “asking the needle”. It never once answered him.] as if the needle could be "
                "**persuaded** to change its mind.",
                "IMAGE",
                "By evening the wind stood at nine on the [Beaufort scale](LINK). It came across the water in long "
                "grey sheets, and the old tower *answered* it with every stone.",
                "## The lamp",
                "She lit the lamp at twenty past five, early, because the light was already going. The flame "
                "caught, steadied, and grew, and the lens took it and threw it out across the water in four white "
                "beams that turned and turned. Whatever else happened tonight, the ships would know where the "
                "rocks were.",
                "It was nearly midnight when she saw the other light. It was small and yellow and low on the "
                "water, far too low for a ship, and it rose and fell with the swell.",
            ]),
            ("03 The Letter", "The Letter", 300, [
                "The stranger slept until noon. When he woke he said his name was Elias, that he had been sailing "
                "to the mainland, and that he was sorry for the trouble.",
                "It was the first of the month, and on the shelf above the stove lay the letter she had been told "
                "to keep closed until today. She opened it while he ate, and read it twice.",
            ]),
            ("04 Low Tide", "Low Tide", 300, [
                "At low tide the island doubled in size. Rocks that had been hidden for twelve hours lay bare and "
                "shining, and between them the old causeway showed itself, stone by stone.",
            ]),
            ("05 The Keeper's Log", "The Keeper's Log", 300, [
                "Here and there, in the margin of the log, her father had drawn a small pencilled star.",
            ]),
            ("06 Fog", "Fog", 300, [
                "The fog came in the night and stayed for three days.",
            ]),
        ],
        "people": [("Ada Morrow", "Keeper of the light, twenty-six."), ("Elias", "Came out of the storm in a rowing boat.")],
        "places_list": [("Skerry Island", "Rock, grass and the tower. A hundred and twelve steps to the lamp.")],
        "idea_list": ["a storm", "a stranger", "a letter that may not be opened yet"],
        "question_list": ["Who taught Elias to row?", "What do the stars in the log mean?"],
    },
    "de": {
        "library": "Schreiben",
        "novel": "Die Leuchtturmwärterin",
        "manuscript": "Manuskript",
        "characters": "Figuren",
        "places": "Orte",
        "notes": "Notizen",
        "ideas": "Ideen",
        "questions": "Offene Fragen",
        "author": "Ada Morrow",
        "draft": "Entwurf",
        "revised": "Überarbeitet",
        "chapter": "Kapitel",
        "caption": "Der Turm am Abend des Sturms",
        "alt": "Ein rot-weißer Leuchtturm auf einer dunklen Insel in der Dämmerung. Sein Licht streicht über "
        "einen wolkigen Himmel, auf dem Meer liegt ein kleines Segelboot.",
        "link": "https://de.wikipedia.org/wiki/Beaufortskala",
        "chapters": [
            ("01 Ankunft", "Ankunft", 250, [
                "Das Boot ließ Ada mit zwei Kisten, einem Sack Mehl und einem Brief auf dem Anleger zurück, den "
                "sie erst am Ersten des Monats öffnen durfte. Der Bootsmann wartete nicht, bis sie den Pfad "
                "hinaufstieg. Er hatte sein eigenes Wetter im Kopf, und die Insel war kein Ort zum Verweilen.",
                "Der Leuchtturm stand oben auf der Anhöhe, weiß vor einem Himmel, der sich nicht zwischen Regen "
                "und Sonne entscheiden konnte. Von unten wirkte er kleiner als auf den Zeichnungen über dem "
                "Schreibtisch ihres Vaters, und älter, als hätte der Wind ihn hundert Jahre lang geschliffen. "
                "Das hatte er.",
                "Drinnen roch die Wärterstube nach Petroleum und Salz. Auf dem Herd stand ein Kessel, kalt. Auf "
                "dem Tisch lag das Logbuch, aufgeschlagen beim letzten Eintrag: *Wind West, mäßig. Lampe "
                "entzündet um 5.40 Uhr. Alles in Ordnung.* Es war die Handschrift ihres Vaters.",
            ]),
            ("02 Der Sturm", "Der Sturm", 250, [
                "Das Barometer fiel seit dem Mittag. Ada klopfte zweimal ans Glas, so wie ihr Vater es immer "
                "getan hatte,^[Er nannte es „die Nadel fragen“. Sie hat ihm nie geantwortet.] als ließe sich die "
                "Nadel **überreden**, es sich anders zu überlegen.",
                "IMAGE",
                "Am Abend stand der Wind bei neun auf der [Beaufortskala](LINK). Er kam in langen grauen Bahnen "
                "über das Wasser, und der alte Turm *antwortete* ihm mit jedem Stein.",
                "## Die Lampe",
                "Sie entzündete die Lampe um zwanzig nach fünf, früh, weil das Licht schon schwand. Die Flamme "
                "fing, wurde ruhig und wuchs, und die Linse nahm sie und warf sie in vier weißen Strahlen über "
                "das Wasser, die sich drehten und drehten. Was auch immer heute Nacht geschah, die Schiffe würden "
                "wissen, wo die Felsen lagen.",
                "Es war fast Mitternacht, als sie das andere Licht sah. Es war klein und gelb und lag tief auf "
                "dem Wasser, viel zu tief für ein Schiff, und es hob und senkte sich mit der Dünung.",
            ]),
            ("03 Der Brief", "Der Brief", 300, [
                "Der Fremde schlief bis zum Mittag. Als er aufwachte, sagte er, er heiße Elias, er sei auf dem "
                "Weg zum Festland gewesen, und es tue ihm leid um die Mühe.",
                "Es war der Erste des Monats, und auf dem Bord über dem Herd lag der Brief, den sie bis heute "
                "geschlossen lassen sollte. Sie öffnete ihn, während er aß, und las ihn zweimal.",
            ]),
            ("04 Ebbe", "Ebbe", 300, [
                "Bei Ebbe wurde die Insel doppelt so groß. Felsen, die zwölf Stunden lang verborgen waren, lagen "
                "nackt und glänzend da, und zwischen ihnen zeigte sich der alte Damm, Stein für Stein.",
            ]),
            ("05 Das Logbuch", "Das Logbuch", 300, [
                "Hier und da hatte ihr Vater einen kleinen Bleistiftstern an den Rand des Logbuchs gezeichnet.",
            ]),
            ("06 Nebel", "Nebel", 300, [
                "Der Nebel kam in der Nacht und blieb drei Tage.",
            ]),
        ],
        "people": [("Ada Morrow", "Leuchtturmwärterin, sechsundzwanzig."), ("Elias", "Kam im Ruderboot aus dem Sturm.")],
        "places_list": [("Skerry", "Fels, Gras und der Turm. Hundertzwölf Stufen bis zur Lampe.")],
        "idea_list": ["ein Sturm", "ein Fremder", "ein Brief, der noch nicht geöffnet werden darf"],
        "question_list": ["Wer hat Elias das Rudern beigebracht?", "Was bedeuten die Sterne im Logbuch?"],
    },
}

# English names of the rows, so a video script can find them in either language
NAMES = {
    language: {
        "The Lighthouse Keeper": t["novel"],
        "Manuscript": t["manuscript"],
        "Characters": t["characters"],
        "Places": t["places"],
        "Notes": t["notes"],
        "Ideas": t["ideas"],
        "Open Questions": t["questions"],
        **{en[0]: own[0] for en, own in zip(TEXT["en"]["chapters"], t["chapters"])},
    }
    for language, t in TEXT.items()
}


def _sheet(path: Path, body: str, **meta) -> None:
    lines = []
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, list):
            value = "[" + ", ".join(value) + "]"
        lines.append(f"{key}: {value}")
    header = "---\n" + "\n".join(lines) + "\n---\n" if lines else ""
    path.write_text(header + body.rstrip() + "\n", encoding="utf-8")


def build(library: Path, language: str = "en", extras: bool = False) -> Path:
    """Fills the folder `library` (it is created) and returns it."""
    t = TEXT[language]
    library.mkdir(parents=True, exist_ok=True)
    novel = library / t["novel"]
    manuscript = novel / t["manuscript"]
    for folder in (manuscript, novel / t["characters"], novel / t["places"], library / t["notes"]):
        folder.mkdir(parents=True, exist_ok=True)

    for number, (name, title, goal, paragraphs) in enumerate(t["chapters"], start=1):
        attachments = manuscript / ".attachments" / name
        parts = []
        for paragraph in paragraphs:
            if paragraph == "IMAGE":
                attachments.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["rsvg-convert", "-w", "1200", str(HERE / "lighthouse.svg"), "-o", str(attachments / "tower.png")],
                    check=True,
                )
                paragraph = f'![{t["caption"]}](<.attachments/{name}/tower.png>){{width=70% alt="{t["alt"]}"}}'
            parts.append(paragraph.replace("(LINK)", f"({t['link']})"))
        _sheet(
            manuscript / f"{name}.md",
            f"# {title}\n\n" + "\n\n".join(parts),
            title=title,
            subtitle=f"{t['chapter']} {number}",
            author=t["author"],
            status=t["revised"] if number == 1 else t["draft"],
            language=language,
            goal=goal,
            keywords=["chapter"] if number > 2 else ["draft", "chapter"],
        )
    order = [f"{name}.md" for name, *_rest in t["chapters"]]
    if extras:
        name, title, subtitle = EXTRAS["chapter"]
        _sheet(manuscript / f"{name}.md", "", title=title, subtitle=subtitle, author=t["author"],
               status=t["draft"], language=language, goal=300, keywords=["chapter"])
        order.append(f"{name}.md")
        for key in ("thesis", "letter"):
            group, sheet, body = EXTRAS[key]
            (library / group).mkdir(exist_ok=True)
            _sheet(library / group / f"{sheet}.md", body, language=language)
    (manuscript / ".typecase.json").write_text(json.dumps({"order": order}), encoding="utf-8")
    for name, line in t["people"]:
        _sheet(novel / t["characters"] / f"{name}.md", f"# {name}\n\n{line}", language=language)
    for name, line in t["places_list"]:
        _sheet(novel / t["places"] / f"{name}.md", f"# {name}\n\n{line}", language=language)
    _sheet(library / t["notes"] / f"{t['ideas']}.md", f"# {t['ideas']}\n\n" + "\n".join(f"- {i}" for i in t["idea_list"]), language=language)
    _sheet(
        library / t["notes"] / f"{t['questions']}.md",
        f"# {t['questions']}\n\n" + "\n".join(f"- {q}" for q in t["question_list"]),
        language=language,
    )
    return library
