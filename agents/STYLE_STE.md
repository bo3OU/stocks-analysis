# Writing style for the brief (STE style, based on ASD-STE100)

Use for `brief.md`. It is a style aid. It is not a certified check against the full ASD-STE100 dictionary. `scripts/ste_lint.py` checks the rules that a script can check.

## Rules
1. One sentence has one idea. Keep it to 20 words or fewer (25 for descriptions that cannot be shorter).
2. Use the active voice. Write "The company raised $575M", not "$575M was raised".
3. Use only the simple past, present and future. Do not use perfect or progressive forms ("has risen", "is rising"). Write "rose" or "rises".
4. Use one word for one meaning. Use a short, common word: use, start, end, show, buy, sell, about, large, small. Do not use: utilize, commence, terminate, approximately, significant, robust, leverage, facilitate, subsequently, furthermore, additionally.
5. Do not omit the words "the", "a" and "an". Do not use more than three nouns in a row.
6. Use a numeral for every number. Write the unit and the date. Write "2026-09-30" or "30 Sep 2026". Do not write "last quarter" without a date.
7. Put one topic in each paragraph. Use no more than 6 sentences in a paragraph.
8. Do not use idioms, figures of speech or hedging chains. State the limit once: "The data covers 13 to 33 weeks."
9. Every sentence with a number ends with a claim ID in brackets: `[FIL-041]`. A fact without a claim ID is not allowed. Mark an own calculation as `[CALC: VAL-007]`. In screen mode (no claims exist) use `[src: tables/financial_summary.md]` or `[src: text/<file>:<line>]` instead.
10. Say what is unknown. Write "Unknown: <what>. <why>." Do not fill a gap with a guess. Do not give a buy, sell or hold call. Do not give one target price.

## Structure of `brief.md` (at most 800 words)
1. **Story.** What the company does and how it makes money. Where it is in its life. (3 to 6 sentences.)
2. **Numbers.** A table: cash, burn per quarter, debt, shares, market value, enterprise value, revenue, cash end date. Each row has a claim ID.
3. **Why the price is what it is.** What the market seems to expect. What the price needs to be true.
4. **What is strong.** Facts with sources.
5. **What is weak or unproven.** Facts with sources.
6. **Money and dilution.** Runway, raises, converts, lock-ups, next dates.
7. **Next dates.** A dated list.
8. **Unknowns and open conflicts.** From the reconciler.
9. **What would change this view.** Two to four tests that anyone can check.

Keep the full detail in `report.md`. Every statement in the brief appears in the report with the same claim ID. Run `ste_lint.py` and fix the findings once.
