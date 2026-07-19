## ADDED Requirements

### Requirement: Course materials load from generative_list API with documents type
The CourseMaterials section SHALL load data from `POST /api/generative_list` with `resource_type: "documents"` instead of constructing fake data from syllabus_list.

#### Scenario: Materials loaded from API display real document cards
- **WHEN** SubjectHome loads with a valid syllabus_id
- **THEN** CourseMaterials receives ResourceSummary[] from the generative_list API with type "documents"

### Requirement: Empty state shown when no document resources exist
When the API returns zero document resources, CourseMaterials SHALL gracefully show nothing (return null) rather than displaying fake/placeholder data.

#### Scenario: No documents available - section hidden
- **WHEN** generative_list returns empty materials array
- **THEN** the CourseMaterials section is not rendered
