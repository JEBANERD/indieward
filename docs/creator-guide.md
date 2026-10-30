# Protect your game from clones: a creator's guide

IndieWard can't stop anyone from copying your game. Nothing can, AI tools included. What it does is make proof cheap and reporting fast, so if a clone shows up today you can send a complete takedown package today. Do the "before launch" steps once per game and the build steps every release.

Not legal advice. Links go to official sources; check them before you rely on a fee or a deadline.

## What actually protects you

- **Enforceable:** a US copyright registration (lets you sue and, if registered in time, claim statutory damages and attorney's fees); a registered trademark; a correct DMCA notice to the store.
- **Evidence:** IndieWard's signed, timestamped certificate; trap markers found in a suspect build; watermarks found in suspect media; fingerprint matches.
- **Deterrents and signals only:** visible watermarks, robots.txt and other "no AI training" signals, pak or PCK encryption. They raise the cost of copying. None of them blocks it.

## Before launch

1. **Install IndieWard and create your vault.** `pipx install "indieward[mcp]"`, then in your game folder: `indieward init --name "<Game>" --creator "<your legal name or studio>" --email <you>`. Back up the `.indieward` folder somewhere private. It holds your keys. It's gitignored, so `git clean -x` (or `-X`) and `git stash --all` delete it; use `git clean -fd`, or add `-e .indieward`.
2. **Prove you control the store page.** Run `indieward status`, paste the verification code into your game's public store description, then `indieward verify page --store itch|steam|roblox --url <page>`. You can remove the code afterward. IndieWard won't register anything until this passes. That makes it harder for someone to register your game in their name and file against you. It can't make it impossible, because the code is open; the certificate records how you verified, so a store can check it.
3. **Register your work in the vault.** `indieward register` your art (`--category art`), UI screens (`--category ui`), logo (`--category logo`), music and sound, trailers and clips, source code, and dialogue or story text. Include your own screenshots. Ship and post the watermarked copies that land in `indieward_out/`. Then run `indieward cert` to sign and timestamp a certificate. If you use asset-store packs or engine templates, run `indieward common add <folder>` on them so shared material never counts as copying.
4. **Register the copyright with the US Copyright Office.** File online through eCO at [copyright.gov/registration](https://www.copyright.gov/registration/). A game is usually registered as a computer program together with its audiovisual work; see [Circular 61](https://www.copyright.gov/circs/circ61.pdf), which also explains how to deposit source code with trade secrets redacted. Fees are listed on the [fee page](https://www.copyright.gov/about/fees.html) (increases were proposed in 2026, so check first).
    - **Do it within 3 months of first publishing, or before any infringement starts.** That keeps statutory damages and attorney's fees available (17 U.S.C. §412). Run `indieward published YYYY-MM-DD` and `indieward status` will count the days down for you.
    - You must register before suing over a US work (17 U.S.C. §411; *Fourth Estate v. Wall-Street.com*, 2019).
    - For smaller disputes, the [Copyright Claims Board](https://ccb.gov) handles claims up to $30,000.
    - Add your registration certificate to the vault: `indieward docs add <file> --kind copyright_registration --title "<Game> registration"`.
5. **Register your trademark** if the name or logo matters commercially. Search existing marks first, then file in [USPTO Trademark Center](https://trademarkcenter.uspto.gov). Games usually file in Class 9 (downloadable game software) and Class 41 (online game services). USPTO fees are per class; check the USPTO site before filing. If you live outside the US, you need a US-licensed attorney to file.
6. **Add trap markers to every build.** `indieward traps new --label "<version>" --engine godot|unity|ue5|roblox|web --out <folder>`. Copy the files into your project as `README_INDIEWARD.txt` in that folder says (don't ship the README), export the build (Godot: in your export preset's Scripts tab, set GDScript Export Mode to Text or Binary tokens, not Compressed binary tokens, which hides the trap strings), then `indieward build register --build <id> <export>` to confirm the traps survived and store the build's fingerprints. Traps are inert: never shown, read once at startup, no network, no player data. Keep the values secret.
7. **Watermark your public media and follow the footage rules.**
    1. Register trailers, clips, screenshots and key art so they get invisible marks, and post the marked copies.
    2. Burn a visible corner mark into every public video, using different text per platform or press contact: `indieward footage burn-in trailer.mp4 trailer_yt.mp4 --text "@studio · YouTube"`.
    3. Post previews at 720p or lower (`indieward footage preview`) and keep the masters private.
    4. Cut trailers so they never show a full level, a full UI layout, a full map, tech tree or shop screen. Show mechanics in short fragments.
    5. On YouTube, leave third-party AI training access off.
    6. On your website, add the AI opt-out lines from `indieward signals robots`. These are requests some crawlers honor, not blocks.
8. **Make ripping harder** (each step only slows a determined ripper):

| Engine | What helps most | Honest rating |
| --- | --- | --- |
| Any | Keep source files (PSD, stems, project files) out of builds; watermark public media | Removes easy wins |
| UE5 | Shipping build with pak/IoStore encryption and signing; keep key logic server-side | Low-moderate: keys can be pulled from the executable |
| Roblox | Keep game logic in ServerScriptService and ServerStorage; thin LocalScripts | The best protection available anywhere: server code never reaches players |
| Unity | IL2CPP instead of Mono, plus an obfuscator | Moderate: IL2CPP can still be dumped |
| Godot | PCK encryption with custom export templates; binary-token GDScript | Low-moderate: the key ships in the binary |
| Web | Server-authoritative logic; assets behind signed URLs; minify | Low for anything sent to the browser |

9. **Sign your builds.** A code signature shows a build came from you and hasn't changed since you signed it. Use [Authenticode](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/authenticode) on Windows; on macOS, sign and [notarize](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) with Apple. A cloner can re-sign a copy with their own certificate, so a signature proves which build is yours, not that a copy isn't.
10. **Keep a visible copyright notice.** Put your copyright line in the credits or about screen, in source file headers and in the build's metadata. `indieward notice` prints all of these for you, plus a short licence notice for AI coding tools. Your name and copyright notice count as copyright management information, and knowingly removing it to enable or hide infringement can be a separate violation ([17 U.S.C. §1202](https://www.copyright.gov/title17/92chap12.html)). IndieWard's checks report when a suspect has your code or art but not your notice.
11. **If you publish your source, your licence decides what others may do with it.** Open-source licences such as [MIT](https://opensource.org/license/mit) and [GPL-3.0](https://opensource.org/license/gpl-3-0) must allow modification and redistribution ([Open Source Definition](https://opensource.org/osd), point 3), so a modified copy that follows the licence is allowed. Source-available licences restrict that. For example, the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license) forbids changing, disabling or circumventing licence-key checks, so removing one breaches the licence. Licences like that aren't open source and aren't on the [OSI list](https://opensource.org/licenses).

## When a clone shows up

1. **Capture evidence now.** Save the store URL, take screenshots, and archive the page with the Wayback Machine ([web.archive.org](https://web.archive.org/)). Note the date and time.
2. **Don't contact, threaten or publicly accuse the cloner.** It can backfire.
3. **Run a check.** `indieward check <suspect build or files> --store-url <their page>`. Use only builds you got legitimately; never pirate or bypass DRM to get one.
4. **Read the filing-strength labels.**
    - **Strong:** trap markers, copied art, copied story or text, copied code.
    - **Supporting:** UI, audio, name or logo, video.
    - **Weak:** mechanics only. Game rules and mechanics aren't protected by copyright (17 U.S.C. §102(b)). A report that rests only on mechanics says so. Don't file it: weak claims get rejected and wear down your credibility with the store.
    - The score measures similarity to your registered work. It can't show whether an AI was used or what any AI read. It's evidence for you to weigh, not a legal finding.
5. **Register your copyright now** if you haven't (step 4 above).
6. **Build the package.** `indieward package --check <id> --url <clone URL>` (it targets only the stores your URLs are on). Read `BEFORE_YOU_SEND.md`, fill in your postal address, phone and signature, and check every claim. Knowingly false claims make you liable for damages (17 U.S.C. §512(f)), and you must consider fair use before sending.
7. **Send it through each store's official channel, from your own account** (table below). IndieWard never sends anything.
8. **Log it:** `indieward takedown sent --check <id> --store <store>`.
9. **If a counter-notice comes**, the store may restore the listing in 10 to 14 business days unless you file a lawsuit (17 U.S.C. §512(g)). Talk to a lawyer at that point.
10. **For your next build**, generate new traps. If a package revealed your core traps, run `indieward traps rotate-core` first.

## Where to report

Checked on 2026-10-28. Open each official page before you send, because stores change these.

| Store | Copyright | Trademark | Official source |
| --- | --- | --- | --- |
| Steam | Web form: [steamcommunity.com/dmca/create](https://steamcommunity.com/dmca/create/) | Same form (no separate channel confirmed) | [Steam DMCA policy](https://store.steampowered.com/legal/dmca) |
| itch.io | Email support@itch.io | Email support@itch.io | [itch.io Terms, DMCA section](https://itch.io/docs/legal/terms#6-digital-millennium-copyright-act); notices are published at [itch.io/takedowns](https://itch.io/takedowns) |
| Roblox | Email copyright_agent@roblox.com, or [Rights Manager](https://create.roblox.com/docs/production/publishing/rights-manager) (18+, ID check) | Email trademark_agent@roblox.com, or Rights Manager | [Roblox IP guidelines](https://create.roblox.com/docs/production/publishing/ip-guidelines) |

Each store's agent is also listed in the US Copyright Office [DMCA Designated Agent Directory](https://www.copyright.gov/dmca-directory/).

## Watch for copies (optional)

`indieward watch run` looks for your trap markers in public code and packages, using official APIs only. Hits are saved as leads (`indieward watch leads`) for you to review. Nothing is filed or sent.

- `--sources swh` (the default) asks [Software Heritage](https://archive.softwareheritage.org/api/) whether your exact trap files or hidden asset are archived. It sends only their hashes, so it reveals nothing readable.
- `--sources github,npm` searches [GitHub code search](https://docs.github.com/en/rest/search/search#search-code) (with your own token in `GITHUB_TOKEN`) and the [npm registry](https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md#get-v1search) for the exact strings. **This sends each string to GitHub or npm**, so you must add `--accept-disclosure`. By default it searches only this build's markers and your public copyright line. `--include-core` also searches the core markers shared by every build, which finds more copies but tells those companies your long-lived markers. If a package or takedown ever reveals them, rotate with `indieward traps rotate-core`.
- npm search covers package names, descriptions and keywords, not the code inside packages.
- Requests are paced to each API's limits. A rate-limit reply stops that source until the next run.

## When to see a lawyer

- You get a counter-notice.
- The clone is making real money, or you want damages.
- The cloner or the store is outside the US.
- You're thinking about a lawsuit.
- Anything in the notice is unclear to you.
- Your players or the cloner are in the EU. There, a licence or EULA can't take away the right to decompile a program when that's needed to make an independent program work with it, and contract terms that try are void ([Directive 2009/24/EC](https://eur-lex.europa.eu/eli/dir/2009/24/oj), Articles 6 and 8). The same article doesn't allow using what's learned to make a substantially similar program.
- The rules depend on where you sue. US appeals courts don't always agree. For example, in September 2026 the Third Circuit held that copying a competitor's editorial material to train a non-generative AI search tool was not fair use, and it distinguished generative-AI training cases ([*Thomson Reuters v. Ross Intelligence*, No. 25-2153](https://www2.ca3.uscourts.gov/opinarch/252153p.pdf)). A lawyer can tell you which court's rules apply to you.

Low-cost options: Volunteer Lawyers for the Arts, law school IP clinics (including the USPTO Law School Clinic Certification Program), and the USPTO Pro Bono Program.

## Sources

- US Copyright Office: [registration](https://www.copyright.gov/registration/) · [fees](https://www.copyright.gov/about/fees.html) · [Circular 61](https://www.copyright.gov/circs/circ61.pdf) · [DMCA Directory](https://www.copyright.gov/dmca-directory/) · [Copyright Claims Board](https://ccb.gov)
- USPTO: [Trademark Center](https://trademarkcenter.uspto.gov)
- Steam: [DMCA policy](https://store.steampowered.com/legal/dmca) · [notice form](https://steamcommunity.com/dmca/create/)
- itch.io: [Terms](https://itch.io/docs/legal/terms#6-digital-millennium-copyright-act) · [published takedowns](https://itch.io/takedowns)
- Roblox: [IP guidelines](https://create.roblox.com/docs/production/publishing/ip-guidelines) · [Rights Manager](https://create.roblox.com/docs/production/publishing/rights-manager)
- Statutes: [17 U.S.C. §102](https://www.law.cornell.edu/uscode/text/17/102) · [§411](https://www.law.cornell.edu/uscode/text/17/411) · [§412](https://www.law.cornell.edu/uscode/text/17/412) · [§512](https://www.law.cornell.edu/uscode/text/17/512) · [§1202](https://www.copyright.gov/title17/92chap12.html)
- EU: [Directive 2009/24/EC on the legal protection of computer programs](https://eur-lex.europa.eu/eli/dir/2009/24/oj)
- Courts: [*Thomson Reuters v. Ross Intelligence*, 3d Cir. No. 25-2153 (2026)](https://www2.ca3.uscourts.gov/opinarch/252153p.pdf)
- Code signing: [Microsoft Authenticode](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/authenticode) · [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- Licences: [Open Source Definition](https://opensource.org/osd) · [OSI-approved licences](https://opensource.org/licenses) · [MIT](https://opensource.org/license/mit) · [GPL-3.0](https://opensource.org/license/gpl-3-0) · [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license)
