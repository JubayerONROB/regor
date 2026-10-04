"""Evidence-grounded manuscript drafting, rendering, auditing and journal preparation.

Marker grammar (used in manuscript/sections/*.md), shared by render and audit:

    {{claim:C001}}              value of a verified claim (with unit)
    {{claimtext:C001}}          the claim's registered text
    0.153 [claim:C001]          a literal checked against claim C001 at written precision
    {{spec:EXP-001:a.b.c}}      a value read from an experiment configuration
    {{project:statistics.alpha}}  a value read from project.yaml
    {{dataset:NAME:version}}    a value read from the dataset manifest entry
    {{table:analysis/comparisons/NAME.json}}      generated table
    {{figure:analysis/visualizations/F.png|Caption}}  figure with provenance check
    [@key] / [@k1; @k2]         citation of a registered reference

Placeholders: [RESEARCHER INPUT REQUIRED], [NEEDS VERIFIED RESULT: ...],
[REFERENCE NOT VERIFIED], [INSUFFICIENT EVIDENCE].
"""
