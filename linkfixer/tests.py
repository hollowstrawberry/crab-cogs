import time
from dataclasses import dataclass

from .linkfixer import ALL_LINKS, DEFAULT_DISABLED_LINKS, fix_links

NAMES = [l.name for l in ALL_LINKS]
DEFAULT_NAMES = [n for n in NAMES if n not in DEFAULT_DISABLED_LINKS]


@dataclass(frozen=True)
class Case:
    src: str
    want: str | None
    only: tuple[str, ...] | None
    lang: str | None
    loose: bool  # ignore trailing punctuation left over from the message


def case(src, want, only: str | tuple[str, ...] | None = None, lang: str | None = None, loose=False):
    if isinstance(only, str):
        new_only = (only,)
    elif only is not None:
        new_only = tuple(only)
    else:
        new_only = None
    return Case(src, want, new_only, lang, loose)


def run_fix_links(src, only=None, lang=""):
    names = DEFAULT_NAMES if only is None else only
    link_types = [l for l in ALL_LINKS if l.name in names]
    result = fix_links(src, link_types, lang)
    return result


LINK_TESTS = [
    # twitter
    case("https://x.com/foo/status/123", "https://fxtwitter.com/foo/status/123", "fxtwitter"),
    case("https://www.twitter.com/foo/status/123?s=20", "https://fxtwitter.com/foo/status/123", "fxtwitter"),
    case("https://mobile.twitter.com/foo/status/1", "https://fxtwitter.com/foo/status/1", "fxtwitter"),
    case("https://m.twitter.com/foo/status/1", "https://fxtwitter.com/foo/status/1", "fxtwitter"),
    case("https://x.com/i/web/status/5", "https://fxtwitter.com/i/web/status/5", "fxtwitter"),
    case("https://x.com/foo/status/123/photo/1", "https://fxtwitter.com/foo/status/123/photo/1", "fxtwitter"),
    case("https://X.com/Foo/status/1", "https://fxtwitter.com/Foo/status/1", "fxtwitter"),
    case("https://x.com/foo/status/123", "https://vxtwitter.com/foo/status/123", "vxtwitter"),
    case("https://x.com/foo/likes", None, "fxtwitter"),
    case("https://x.com/foo", None, "fxtwitter"),
    case("https://fxtwitter.com/foo/status/1", None, "fxtwitter"),
    # instagram
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC", "oginstagram"),
    case("https://www.instagram.com/p/ABC/", "https://vxinstagram.com/p/ABC", "vxinstagram"),
    case("https://www.instagram.com/p/ABC/", "https://kkinstagram.com/p/ABC", "kkinstagram"),
    case("https://instagram.com/reel/XYZ/?igsh=1", "https://kkinstagram.com/reel/XYZ", "kkinstagram"),
    case("https://instagram.com/someuser/", None, "kkinstagram"),
    case("https://instagram.com/reels/ABC/", "https://kkinstagram.com/reels/ABC", "kkinstagram"),
    case("https://instagram.com/tv/ABC/", "https://kkinstagram.com/tv/ABC", "kkinstagram"),
    case("https://instagram.com/someuser/p/ABC/", "https://kkinstagram.com/someuser/p/ABC", "kkinstagram"),
      #case("https://instagram.com/someuser/reels/", None, "kkinstagram"),
      #case("https://instagram.com/someuser/tagged/", None, "kkinstagram"),
      #case("https://instagram.com/stories/someuser/123/", None, "kkinstagram"),
      #case("https://instagram.com/explore/tags/cats/", None, "kkinstagram"),
      #case("https://instagram.com/p/", None, "kkinstagram"),
    # reddit
    case("https://www.reddit.com/r/foo/comments/abc/title/", "https://vxreddit.com/r/foo/comments/abc/title", "vxreddit"),
    case("https://old.reddit.com/r/foo/comments/abc", "https://vxreddit.com/r/foo/comments/abc", "vxreddit"),
    case("https://reddit.com/r/foo/s/abc", "https://vxreddit.com/r/foo/s/abc", "vxreddit"),
    case("https://www.reddit.com/r/foo/comments/abc/title/", "https://redditez.com/r/foo/comments/abc/title", "redditez"),
    # pixiv
    case("https://www.pixiv.net/en/artworks/123", "https://phixiv.net/en/artworks/123", "phixiv"),
    case("https://www.pixiv.net/en/artworks/123", "https://ppxiv.net/en/artworks/123", "ppxiv"),
    case("https://www.pixiv.net/", None, "phixiv"),
    # threads
    case("https://www.threads.com/@u/post/ABC", "https://viewthreads.com/@u/post/ABC", "viewthreads"),
    case("https://www.threads.net/@u/post/ABC", "https://viewthreads.com/@u/post/ABC", "viewthreads"),
    case("https://www.threads.com/@u", None, "viewthreads"),
    # tiktok
    case("https://www.tiktok.com/@u/video/123", "https://www.tnktok.com/@u/video/123", "tnktok"),
    case("https://tiktok.com/@u/video/123", "https://tnktok.com/@u/video/123", "tnktok"),
    case("https://vm.tiktok.com/ZM123/", "https://vm.tnktok.com/ZM123", "tnktok"),
    case("https://vt.tiktok.com/ZS9/", "https://vt.tnktok.com/ZS9", "tnktok"),
    case("https://www.tiktok.com/t/ZT123/", "https://www.tnktok.com/t/ZT123", "tnktok"),
    case("https://www.tiktok.com/@u/video/123?is_from_webapp=1", "https://www.tnktok.com/@u/video/123", "tnktok"),
    case("https://tiktok.com/@u/ look at this/ok", None, "tnktok"),  # whitespace must not be glued into a link
    case("https://www.tiktok.com/@u/video/123", "https://www.tiktokez.com/@u/video/123", "tiktokez"),
    # bilibili
    case("https://www.bilibili.com/video/BV1x", "https://www.vxbilibili.com/video/BV1x", "vxbilibili"),
    case("https://bilibili.com/video/BV1x", "https://vxbilibili.com/video/BV1x", "vxbilibili"),
    case("https://b23.tv/abc", "https://vxb23.tv/abc", "vxb23"),
    # fixembed (the query is stripped *before* it is embedded, so there is no unencoded & or ?)
    case("https://x.com/foo/status/123", "https://fixembed.app/embed?url=https://x.com/foo/status/123", "fixembed"),
    case("https://x.com/foo/status/123?s=20&a=1", "https://fixembed.app/embed?url=https://x.com/foo/status/123", "fixembed"),
    case("https://old.reddit.com/r/a/comments/1", "https://fixembed.app/embed?url=https://old.reddit.com/r/a/comments/1", "fixembed"),
    case("https://youtube.com/post/abc", "https://fixembed.app/embed?url=https://youtube.com/post/abc", "fixembed"),
    case("https://pin.it/abc", "https://fixembed.app/embed?url=https://pin.it/abc", "fixembed"),
    case("https://redd.it/abc", "https://fixembed.app/embed?url=https://redd.it/abc", "fixembed"),
    case("https://youtube.com/watch?v=abc", None, "fixembed"),
    case("https://fixembed.app/embed?url=https://x.com/a/status/1", None, "fixembed"),
]


DEFAULTS_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1"),
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC"),
    case("https://www.reddit.com/r/foo/comments/abc/t/", "https://vxreddit.com/r/foo/comments/abc/t"),
    case("https://www.pixiv.net/en/artworks/123", "https://phixiv.net/en/artworks/123"),
    case("https://www.threads.com/@u/post/ABC", "https://viewthreads.com/@u/post/ABC"),
    case("https://www.tiktok.com/@u/video/123", "https://www.tnktok.com/@u/video/123"),
    case("https://www.bilibili.com/video/BV1x", "https://www.vxbilibili.com/video/BV1x"),
    case("https://b23.tv/abc", "https://vxb23.tv/abc"),
    case("https://www.pinterest.com/pin/123/", "https://fixembed.app/embed?url=https://www.pinterest.com/pin/123"),
    case("https://fixembed.app/embed?url=https://x.com/a/status/1", None),   # never wrap twice
    case("<https://x.com/foo/status/1>", None),                              # <link> = embed suppressed on purpose
    case("https://x.com/a/status/1 https://www.instagram.com/p/ABC https://www.reddit.com/r/foo/comments/abc/t/",
      "https://fxtwitter.com/a/status/1\nhttps://oginstagram.com/p/ABC\nhttps://vxreddit.com/r/foo/comments/abc/t"),
]


SPOILERS_TESTS = [
    case("||https://x.com/foo/status/1||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("||https://x.com/foo/status/1?s=20||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("|| https://x.com/foo/status/1 ||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("||https://x.com/foo/status/1||", "|| https://fxtwitter.com/foo/status/1/en ||", lang="en"),
    case("https://x.com/a/status/1 ||https://x.com/b/status/2||",
      "https://fxtwitter.com/a/status/1\n|| https://fxtwitter.com/b/status/2 ||"),
    case("||https://x.com/b/status/2|| https://x.com/a/status/1",
      "|| https://fxtwitter.com/b/status/2 ||\nhttps://fxtwitter.com/a/status/1"),
    case("https://x.com/a/status/1 ||https://x.com/a/status/1||", "|| https://fxtwitter.com/a/status/1 ||"),  # spoiler wins on dupes
    case("||https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),   # unclosed || is not a spoiler
    case("`||` https://x.com/a/status/1", "|| https://fxtwitter.com/a/status/1 ||"),  # the Android quirk in fix_links
]


CODEBLOCK_TESTS = [
    case("`https://x.com/a/status/1`", None),
    case("```https://x.com/a/status/1```", None),
    case("```\nhttps://x.com/a/status/1\n```", None),
    case("`https://x.com/a/status/1` https://x.com/b/status/2", "https://fxtwitter.com/b/status/2"),
    case("`https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),   # unclosed backtick is literal text
]


MULTILINK_TESTS = [
    case("https://x.com/a/status/1 https://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("https://x.com/a/status/1\nhttps://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("look: https://x.com/a/status/1\nand https://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("https://x.com/a/status/1 https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),
    case("https://x.com/a/status/1 https://example.com/page", "https://fxtwitter.com/a/status/1\nhttps://example.com/page"),
    case("https://example.com/page", None),
    case("just some text", None),
    case("", None),
]


TRANSLATION_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1/", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1?s=20", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", lang=""),
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", lang=None),  # config default is None
    case("https://www.reddit.com/r/foo/comments/abc/t/", "https://vxreddit.com/r/foo/comments/abc/t", lang="en"),
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC", lang="en"),
    case("https://x.com/a/status/1 https://www.reddit.com/r/foo/comments/abc/t/",
      "https://fxtwitter.com/a/status/1/en\nhttps://vxreddit.com/r/foo/comments/abc/t", lang="en"),
]


SELECTION_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", only=("vxtwitter", "fxtwitter")),
    case("https://www.instagram.com/p/ABC/", "https://vxinstagram.com/p/ABC", only=("kkinstagram", "vxinstagram")),
    case("https://x.com/foo/status/1", "https://fixembed.app/embed?url=https://x.com/foo/status/1", only=("fixembed",)),
    case("https://x.com/foo/status/1", None, only=()),
]


ROBUSTNESS_TESTS = [
    case("https://x.com.evil.com/foo/status/1", None),
    case("https://evil.com/x.com/foo/status/1", None),
    case("https://nottwitter.com/foo/status/1", None),
    case("https://example.com/r/https://x.com/a/status/1", None),     # url embedded in another url's path
    case("https://example.com/?u=https://x.com/a/status/1", None),    # ...or its query
    case("(https://x.com/a/status/1)", "https://fxtwitter.com/a/status/1"),
    case("[t](https://x.com/foo/status/1)", "https://fxtwitter.com/foo/status/1"),
    case("https://X.COM/Foo/Status/1", "https://fxtwitter.com/Foo/Status/1"),
]


PUNCTUATION_TESTS = [
    case("see https://x.com/foo/status/1.", "https://fxtwitter.com/foo/status/1", loose=True),
    case("wow https://x.com/a/status/1, nice", "https://fxtwitter.com/a/status/1", loose=True),
    case("is it https://x.com/a/status/1?", "https://fxtwitter.com/a/status/1", loose=True),
    case("https://x.com/a/status/1!!", "https://fxtwitter.com/a/status/1", loose=True),
]


TEST_SUITES = {
    "per-link": LINK_TESTS,
    "default set": DEFAULTS_TESTS,
    "spoilers": SPOILERS_TESTS,
    "code blocks": CODEBLOCK_TESTS,
    "multiple links": MULTILINK_TESTS,
    "language": TRANSLATION_TESTS,
    "selection": SELECTION_TESTS,
    "robustness": ROBUSTNESS_TESTS,
    "punctuation": PUNCTUATION_TESTS,
}


KNOWN_BUGS = [
    ("bilibili part number (?p=2) is dropped", "https://www.bilibili.com/video/BV1x?p=2"),
    ("instagram carousel index (?img_index=2) is dropped", "https://www.instagram.com/p/ABC/?img_index=2"),
    ("legacy pixiv url loses the query it depends on", "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=123"),
    ("some instagram urls are matched when they are not posts", "https://www.instagram.com/someuser/reels"),
]


def run_suite(name: str, cases: list[Case]):
    failed = 0
    for case in cases:
        try:
            got = run_fix_links(case.src, case.only, case.lang or "")
        except Exception as e:  # bad group names, wrong signature, etc.
            got = f"ERROR {type(e).__name__}: {e}"
        cmp = got.rstrip(".,;:!?") if (case.loose and isinstance(got, str)) else got
        if cmp != case.want:
            failed += 1
            print(f"FAIL [{name}]")
            print(f"   in:    {case.src!r}")
            if case.only is not None:
                print(f"   only:  {case.only}")
            if case.lang:
                print(f"   lang:  {case.lang!r}")
            print(f"   want:  {case.want!r}")
            print(f"   got:   {got!r}")
    return failed


def check_registry():
    problems = []
    if len(set(NAMES)) != len(NAMES):
        problems.append("duplicate link names in ALL_LINKS")
    unknown = set(DEFAULT_DISABLED_LINKS) - set(NAMES)
    if unknown:
        problems.append(f"DEFAULT_DISABLED_LINKS has names that are not links: {sorted(unknown)}")
    tested = {cs.only[0] for cs in TEST_SUITES["per-link"] if cs.only and len(cs.only) == 1}
    untested = [n for n in NAMES if n not in tested]
    if untested:
        problems.append(f"links with no per-link test: {untested}")
    for p in problems:
        print(f"FAIL [registry] {p}")
    return len(problems)


def check_performance():
    """Pathological input must not hang the bot's event loop."""
    failed = 0
    inputs = {
        "very long path, no /status/": "https://x.com/" + "a/" * 20000,
        "very long query string": "https://x.com/u/status/1?" + "a=b&" * 20000,
        "300 links in one message": " ".join(f"https://x.com/u/status/{i}" for i in range(300)),
    }
    for label, src in inputs.items():
        start = time.perf_counter()
        try:
            got = run_fix_links(src)
        except Exception as e:
            print(f"FAIL [performance] {label}: ERROR {type(e).__name__}: {e}")
            failed += 1
            continue
        elapsed = time.perf_counter() - start
        if elapsed > 2.0:
            print(f"FAIL [performance] {label}: took {elapsed:.1f}s which is above 2000")
            failed += 1
        if label.startswith("300") and (got is None or got.count("\n") != 299):
            print(f"FAIL [performance] {label}: expected 300 lines")
            failed += 1
    return failed


def main():
    failed = check_registry()
    total = 0
    for name, cases in TEST_SUITES.items():
        total += len(cases)
        failed += run_suite(name, cases)
    failed += check_performance()
    print(f"\n{total} cases in {len(TEST_SUITES)} suites, plus registry and performance checks: "
          f"{'all passed' if not failed else f'{failed} FAILED'}")

    print("\nTODO fix bugs:")
    for label, src in KNOWN_BUGS:
        print(f"  {label}\n     {src!r} -> {run_fix_links(src)!r}")
    return failed


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
