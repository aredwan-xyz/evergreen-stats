#!/usr/bin/env python3
"""evergreen-stats — self-hosted GitHub profile stat cards.

Generates a stats card and a top-languages card as plain SVG, computed
entirely from the GitHub REST API inside your own Action run. No external
rendering service, no shared rate limit, nothing that can 503 on you.

Usage:
    python3 generate.py --user <github-username> --out ./assets [options]

Env:
    GITHUB_TOKEN / GH_TOKEN   used for API auth if set (raises the rate limit
                              from 60/hr to 5000/hr — set this in your workflow)
"""

import argparse
import json
import os
import urllib.request

API = "https://api.github.com"

# A compact linguist-style color map. Falls back to a neutral gray for
# anything not listed — this is intentionally not exhaustive.
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "HTML": "#e34c26", "CSS": "#563d7c", "Java": "#b07219", "C++": "#f34b7d",
    "C": "#555555", "C#": "#178600", "Go": "#00ADD8", "Rust": "#dea584",
    "Ruby": "#701516", "PHP": "#4F5D95", "Swift": "#F05138", "Kotlin": "#A97BFF",
    "Shell": "#89e051", "Vue": "#41b883", "Dart": "#00B4AB", "Dockerfile": "#384d54",
    "Jupyter Notebook": "#DA5B0B", "Scala": "#c22d40", "Elixir": "#6e4a7e",
}
DEFAULT_LANG_COLOR = "#8b949e"

THEMES = {
    "dark":  dict(bg="#0d1117", border="#30363d", title="#58a6ff", text="#c9d1d9", icon="#58a6ff"),
    "light": dict(bg="#ffffff", border="#e1e4e8", title="#0969da", text="#24292f", icon="#0969da"),
}


def gh(path, token):
    req = urllib.request.Request(
        API + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "evergreen-stats"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(user, token):
    profile = gh(f"/users/{user}", token)
    repos = gh(f"/users/{user}/repos?per_page=100&type=owner", token)
    repos = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in repos)

    langs = {}
    for r in repos:
        try:
            data = gh(f"/repos/{r['full_name']}/languages", token)
        except Exception:
            continue
        for name, byts in data.items():
            langs[name] = langs.get(name, 0) + byts

    return {
        "public_repos": profile.get("public_repos", len(repos)),
        "followers": profile.get("followers", 0),
        "stars": stars,
        "created_at": profile.get("created_at", ""),
        "langs": sorted(langs.items(), key=lambda kv: -kv[1])[:6],
    }


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stats_card(user, data, theme, overrides):
    t = {**THEMES[theme], **overrides}
    rows = [
        ("Public Repos", data["public_repos"]),
        ("Stars Earned", data["stars"]),
        ("Followers", data["followers"]),
    ]
    if data["created_at"]:
        year = data["created_at"][:4]
        rows.append(("On GitHub Since", year))

    row_svgs = []
    y = 74
    for label, value in rows:
        row_svgs.append(
            f'<text x="25" y="{y}" font-family="Helvetica,Arial,sans-serif" font-size="14" fill="{t["text"]}">{esc(label)}</text>'
            f'<text x="470" y="{y}" text-anchor="end" font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="700" fill="{t["title"]}">{esc(value)}</text>'
        )
        y += 28

    height = max(195, y + 10)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}" role="img" aria-label="{esc(user)}'s GitHub Stats">
  <rect x="0.5" y="0.5" width="494" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>
  <text x="25" y="35" font-family="Helvetica,Arial,sans-serif" font-size="16" font-weight="700" fill="{t["title"]}">{esc(user)}'s GitHub Stats</text>
  {"".join(row_svgs)}
</svg>
'''


def langs_card(user, data, theme, overrides):
    t = {**THEMES[theme], **overrides}
    langs = data["langs"]
    total = sum(v for _, v in langs) or 1

    rows = []
    y = 70
    bar_w = 300
    for name, byts in langs:
        pct = byts / total * 100
        filled = round(pct / 100 * bar_w)
        color = LANG_COLORS.get(name, DEFAULT_LANG_COLOR)
        rows.append(
            f'<text x="25" y="{y}" font-family="Helvetica,Arial,sans-serif" font-size="13" fill="{t["text"]}">{esc(name)}</text>'
            f'<rect x="150" y="{y - 12}" width="{bar_w}" height="10" rx="5" fill="{t["border"]}"/>'
            f'<rect x="150" y="{y - 12}" width="{filled}" height="10" rx="5" fill="{color}"/>'
            f'<text x="{150 + bar_w + 10}" y="{y}" font-family="Helvetica,Arial,sans-serif" font-size="12" fill="{t["text"]}">{pct:.1f}%</text>'
        )
        y += 26

    height = max(195, y + 10)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}" role="img" aria-label="{esc(user)}'s most used languages">
  <rect x="0.5" y="0.5" width="494" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>
  <text x="25" y="35" font-family="Helvetica,Arial,sans-serif" font-size="16" font-weight="700" fill="{t["title"]}">Most Used Languages</text>
  {"".join(rows)}
</svg>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--out", default="./assets")
    ap.add_argument("--theme", default="dark", choices=list(THEMES))
    ap.add_argument("--bg-color")
    ap.add_argument("--title-color")
    ap.add_argument("--text-color")
    ap.add_argument("--border-color")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    overrides = {}
    if args.bg_color: overrides["bg"] = args.bg_color
    if args.title_color: overrides["title"] = args.title_color
    if args.text_color: overrides["text"] = args.text_color
    if args.border_color: overrides["border"] = args.border_color

    data = fetch(args.user, token)
    os.makedirs(args.out, exist_ok=True)

    with open(os.path.join(args.out, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_card(args.user, data, args.theme, overrides))
    with open(os.path.join(args.out, "languages.svg"), "w", encoding="utf-8") as f:
        f.write(langs_card(args.user, data, args.theme, overrides))

    print(f"Wrote {args.out}/stats.svg and {args.out}/languages.svg for {args.user}")


if __name__ == "__main__":
    main()
