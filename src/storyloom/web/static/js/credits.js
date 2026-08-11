/* ═══════════════════════════════════════════════════════════════════
   credits.js — About data: project links + contributors

   Each person:  { name, url }  — url is rendered as a clickable link.
   Each link:    { label, url, desc } — label is the i18n msgid.

   Authority: storyloom.po (translations)
   ═══════════════════════════════════════════════════════════════════ */

const CREDITS = {
    /** Project & Community links — rendered as a card above Contributors. */
    links: [
        {
            label: "Source Code",
            url: "https://github.com/SiriLee/Storyloom",
            desc: "GitHub repository — star, fork, and explore the code.",
        },
        {
            label: "Issue Tracker",
            url: "https://github.com/SiriLee/Storyloom/issues",
            desc: "Report bugs, request features, or share feedback.",
        },
    ],
    contributors: [
        {name: "Slev", url: "https://github.com/SiriLee"},
        {name: "Claude", url: "https://github.com/claude"},
        {name: "yupaoa", url: "https://github.com/yupaoa"},
    ],
};
