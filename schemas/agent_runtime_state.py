from extensions import db


class LearningPlan(db.Model):
    __tablename__ = "learning_plan"

    plan_id = db.Column(db.String(80), primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    syllabus_id = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, default="active", index=True)
    source = db.Column(db.String(80), nullable=False, default="recommendation")
    candidate_index = db.Column(db.Integer, nullable=True)
    path_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.Integer, nullable=False, default=0)


class LearningPlanStep(db.Model):
    __tablename__ = "learning_plan_step"

    step_id = db.Column(db.String(80), primary_key=True)
    plan_id = db.Column(db.String(80), db.ForeignKey("learning_plan.plan_id"), nullable=False, index=True)
    node_id = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(255), nullable=True)
    outcomes_json = db.Column(db.Text, nullable=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(40), nullable=False, default="pending", index=True)
    resource_ids_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("plan_id", "order_index", name="uq_learning_plan_step_order"),
    )


class LearningPlanEvent(db.Model):
    __tablename__ = "learning_plan_event"

    entry_id = db.Column(db.String(80), primary_key=True)
    plan_id = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    syllabus_id = db.Column(db.Integer, nullable=True, index=True)
    step_id = db.Column(db.String(80), nullable=True, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=True)
    source = db.Column(db.String(80), nullable=True)
    payload_json = db.Column(db.Text, nullable=True)
    schema_version = db.Column(db.String(40), nullable=False, default="learning_plan.v1")
    created_at = db.Column(db.Integer, nullable=False, default=0)


class GeneratedResource(db.Model):
    __tablename__ = "generated_resource"

    resource_id = db.Column(db.String(120), primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    syllabus_id = db.Column(db.Integer, nullable=True, index=True)
    step_id = db.Column(db.String(80), nullable=True, index=True)
    resource_type = db.Column(db.String(60), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    topic = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="ready")
    resource_dir = db.Column(db.String(512), nullable=True)
    validation_json = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    main_files_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.Integer, nullable=False, default=0)


class GeneratedResourceFile(db.Model):
    __tablename__ = "generated_resource_file"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    resource_id = db.Column(db.String(120), db.ForeignKey("generated_resource.resource_id"), nullable=False, index=True)
    file_role = db.Column(db.String(80), nullable=False)
    path_or_url = db.Column(db.String(512), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("resource_id", "file_role", name="uq_generated_resource_file_role"),
    )


class StudyGraphTree(db.Model):
    __tablename__ = "study_graph_tree"

    tree_id = db.Column(db.String(120), primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    syllabus_id = db.Column(db.Integer, nullable=False, index=True)
    subject_title = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(255), nullable=True)
    summary_json = db.Column(db.Text, nullable=True)
    manifest_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("user_id", "syllabus_id", name="uq_study_graph_tree_user_syllabus"),
    )


class StudyGraphNode(db.Model):
    __tablename__ = "study_graph_node"

    node_id = db.Column(db.String(160), primary_key=True)
    tree_id = db.Column(db.String(120), db.ForeignKey("study_graph_tree.tree_id"), nullable=False, index=True)
    type = db.Column(db.String(40), nullable=False, default="knowledge")
    title = db.Column(db.String(255), nullable=False)
    normalized_title = db.Column(db.String(255), nullable=False)
    aliases_json = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    parent_node_id = db.Column(db.String(160), nullable=True)
    mastery_json = db.Column(db.Text, nullable=True)
    mastery_label = db.Column(db.String(40), nullable=True, index=True)
    mastery_score = db.Column(db.Float, nullable=True)
    display_json = db.Column(db.Text, nullable=True)
    source_json = db.Column(db.Text, nullable=True)
    first_seen_at = db.Column(db.Integer, nullable=False, default=0)
    last_updated_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("tree_id", "normalized_title", name="uq_study_graph_node_normalized"),
    )


class StudyGraphEdge(db.Model):
    __tablename__ = "study_graph_edge"

    edge_id = db.Column(db.String(512), primary_key=True)
    tree_id = db.Column(db.String(120), db.ForeignKey("study_graph_tree.tree_id"), nullable=False, index=True)
    source_node_id = db.Column(db.String(160), nullable=False)
    target_node_id = db.Column(db.String(160), nullable=False)
    edge_type = db.Column(db.String(60), nullable=False, default="parent_of")
    created_at = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("tree_id", "source_node_id", "target_node_id", "edge_type", name="uq_study_graph_edge"),
    )


class StudyGraphChangeLog(db.Model):
    __tablename__ = "study_graph_change_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tree_id = db.Column(db.String(120), db.ForeignKey("study_graph_tree.tree_id"), nullable=False, index=True)
    client_change_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(60), nullable=True)
    request_json = db.Column(db.Text, nullable=True)
    result_json = db.Column(db.Text, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    entry_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("tree_id", "client_change_id", name="uq_study_graph_change_client"),
    )

