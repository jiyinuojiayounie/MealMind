# Development recipe catalog

`catalog-v1.json` holds original AI-assisted development drafts. All 20 recipes are draft records. Standard quantities and times are illustrative. Empty dietary and allergen maps mean the relevant claims are unknown. Household conversions, reuse clearance, and independent review are pending.

Use the Python catalog loader with an explicit file path. The bundled path is available as `DEVELOPMENT_CATALOG_PATH`. Production retrieval excludes draft and retired records. When an allergen is excluded, eligibility requires reviewed evidence at the recipe and ingredient levels. The eligibility check does not establish cross-contact safety.

Keep recipe and ingredient IDs stable across catalog revisions. Increment the recipe revision for material recipe changes and the catalog version for a new snapshot. The schema version identifies the file format. Create an updated snapshot in a new versioned file and preserve IDs for existing records.

## Catalog version 2

The development loader now uses `catalog-v2.json`. Version 1 remains the snapshot referenced by batch review 01. Version 2 records clear process-water uses separately and flags cooked rice as a required starting ingredient for the two rice combinations. The steamer-water volume for steamed eggs remains unknown. All 12 selected recipes carry verification notes and remain drafts.

Use edible portion weight as the target basis for gram quantities, with each ingredient's stated preparation state. Legacy draft weights and all timing estimates still require cook-through review. No amounts, times, household conversions, or safety evidence were certified in this version.

## Catalog version 3

The development loader now uses `catalog-v3.json`. This revision prepares the 12 batch 01 selections for human review and preserves the other eight records. It adds provisional flavor descriptions, serving context and revised instructions. All records remain drafts. Time, ingredient amount, allergen, household-measure and reuse verification remains pending. See the [release candidate review cards](../../docs/RECIPE_RELEASE_CANDIDATE_01.md).

## Catalog version 4

The development loader uses `catalog-v4.json`. This snapshot preserves the earlier recipe and family IDs, identifies the equipment and separately heated components implied by the draft steps, and adds six one-person recipes. A zero time or component count is used only for a no-cook draft. Absence of the new metadata remains valid on old snapshots. Ingredient screening for an explicit vegetarian preference is provisional. Strict dietary and allergen eligibility still need reviewed evidence. See the [full audit and offline comparison](../../docs/RECIPE_CATALOG_PRACTICALITY_AUDIT.md).
