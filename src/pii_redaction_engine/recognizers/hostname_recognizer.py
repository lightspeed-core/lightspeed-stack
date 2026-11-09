"""Custom Presidio recognizer for hostnames / FQDNs."""

from typing import Optional

from presidio_analyzer import Pattern, PatternRecognizer


class HostnameRecognizer(PatternRecognizer):
    """Recognize hostnames / FQDNs using regex."""

    # A DNS label: 1-63 alphanumerics or hyphens, not starting or ending with one.
    LABEL = r"(?:(?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)"

    # Country code TLDs, so that "www.symbolblog.at" is recognised as a hostname
    # rather than left to spaCy, which reports it as a location.
    CCTLDS = (
        "ac ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg "
        "bh bi bj bm bn bo br bs bt bw by bz ca cc cd cf cg ch ci ck cl cm cn "
        "co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg er es et eu fi fj "
        "fk fm fo fr ga gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk "
        "hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki "
        "km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg "
        "mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni "
        "nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re "
        "ro rs ru rw sa sb sc sd se sg sh si sk sl sm sn so sr ss st sv sx sy "
        "sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz "
        "va vc ve vg vi vn vu wf ws ye yt za zm zw"
    ).split()

    # ccTLDs that are also common source and config file extensions. "main.py" and
    # "mysite.py" are the same shape, so nothing in the text separates them, and the
    # choice is which way to be wrong. These need a subdomain to count as a host:
    # "docs.example.py" matches, "main.py" does not.
    #
    # The cost is real: a bare two label domain on one of these, "bankofchisinau.md",
    # is not redacted, and spaCy does not reliably catch it either. That is accepted
    # because support text carries filenames constantly and Moldovan domains almost
    # never, and because a leaked hostname is recoverable by tightening this list
    # while a redacted traceback is just gone. Revisit if real hosts start appearing
    # on these TLDs.
    FILE_EXTENSION_CCTLDS = {
        "as",
        "cc",
        "md",
        "pl",
        "pm",
        "ps",
        "py",
        "rs",
        "sh",
        "tf",
    }

    # TLDs of three or more characters, including the internal-only names that appear
    # in customer estates. No file extension collides with these at this length.
    LONG_TLDS = (
        "com net org edu gov mil int biz info tech dev cloud app example local "
        "internal localhost intra lab ocm"
    ).split()

    _SAFE_CC = "|".join(sorted(set(CCTLDS) - FILE_EXTENSION_CCTLDS))
    _EXT_CC = "|".join(sorted(FILE_EXTENSION_CCTLDS))
    _LONG = "|".join(LONG_TLDS)

    HOSTNAME_REGEX = (
        rf"\b(?:{LABEL}+(?:{_SAFE_CC})"
        rf"|{LABEL}{{2,}}(?:{_EXT_CC})"
        rf"|{LABEL}+(?:{_LONG}))\b"
    )

    PATTERNS = [Pattern("Hostname pattern", HOSTNAME_REGEX, 1)]

    CONTEXT = ["host", "hostname", "server", "node"]

    def __init__(
        self,
        patterns: Optional[list[Pattern]] = None,
        context: Optional[list[str]] = None,
        supported_language: str = "en",
        supported_entity: str = "HOSTNAME",
    ):
        """Initialize the hostname recognizer with its default pattern and context."""
        patterns = patterns if patterns else self.PATTERNS
        context = context if context else self.CONTEXT
        super().__init__(
            supported_entity=supported_entity,
            patterns=patterns,
            context=context,
            supported_language=supported_language,
        )
