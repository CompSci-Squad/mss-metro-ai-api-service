"""Prompts contextuais com histórico de análises e engenharia avançada."""

from datetime import datetime

import structlog

from app.services.hallucination_mitigation import PromptTemplates

logger = structlog.get_logger(__name__)


class ContextualPromptBuilder:
    """Constrói prompts contextuais para análise de imagens BIM."""

    def __init__(self, enable_contextual: bool = True):
        self.enable_contextual = enable_contextual
        self.prompt_templates = PromptTemplates()

    async def build_analysis_prompt(
        self,
        project_context: dict | None = None,
        rag_context: list | None = None,
        temporal_context: dict | None = None
    ) -> str:
        """Constrói prompt contextual dinâmico para análise de imagem.

        Args:
            project_context: Contexto do projeto (nome, localização, etc)
            rag_context: Elementos relevantes do BIM encontrados via RAG
            temporal_context: Análise anterior (progresso, elementos detectados)

        Returns:
            Prompt formatado com contexto BIM, RAG e temporal
        """
        prompt_parts = [
            "[BIM ANALYSIS TASK]",
            "You are analyzing a construction site image using BIM context.",
            ""
        ]

        # 1. BIM Reference Context
        if rag_context and len(rag_context) > 0:
            prompt_parts.append("[BIM REFERENCE CONTEXT]")
            prompt_parts.append("Expected elements from BIM model:")
            
            element_types = {}
            for elem in rag_context[:10]:  # Top 10 mais relevantes
                elem_type = elem.get('element_type', 'Unknown')
                elem_name = elem.get('element_name', 'Unnamed')
                if elem_type not in element_types:
                    element_types[elem_type] = []
                element_types[elem_type].append(elem_name)
            
            for elem_type, names in element_types.items():
                names_str = ', '.join(names[:3])  # Primeiros 3
                count = len(names)
                prompt_parts.append(f"- {elem_type}: {names_str} ({count} total)")
            
            prompt_parts.append("")

        # 2. Temporal Context
        if temporal_context:
            prompt_parts.append("[TEMPORAL CONTEXT]")
            prompt_parts.append(f"Previous analysis: {temporal_context.get('timestamp')}")
            prompt_parts.append(f"Progress: {temporal_context.get('overall_progress')}% | Phase: {temporal_context.get('construction_phase')}")
            prompt_parts.append("")
            
            completed = [e for e in temporal_context.get("detected_elements", []) if e.get("status") == "completed"]
            in_progress = [e for e in temporal_context.get("detected_elements", []) if e.get("status") == "in_progress"]
            
            if completed:
                prompt_parts.append("COMPLETED: " + ", ".join([e.get("element_name", "?") for e in completed[:5]]))
            if in_progress:
                prompt_parts.append("IN PROGRESS: " + ", ".join([e.get("element_name", "?") for e in in_progress[:5]]))
            
            prompt_parts.append("")
            
            prompt_parts.append("FOCUS:")
            prompt_parts.append("1. Verify IN PROGRESS elements are now COMPLETED")
            prompt_parts.append("2. Identify NEW elements")
            prompt_parts.append("3. Confirm COMPLETED elements remain completed")
            prompt_parts.append(f"4. Expected progress: +{min(temporal_context.get('days_since', 0) * 2, 20):.0f}% based on {temporal_context.get('days_since', 0)} days")
        
        # 3. Project Context
        if project_context:
            prompt_parts.append("[PROJECT CONTEXT]")
            prompt_parts.append(f"Project: {project_context.get('project_name', 'Unknown')}")
            prompt_parts.append(f"Location: {project_context.get('location', 'Unknown')}")
            prompt_parts.append("")
        
        # 4. Visual Analysis Task with Anti-Hallucination Rules
        prompt_parts.extend([
            "[VISUAL ANALYSIS TASK]",
            "Analyze the construction image following these CRITICAL rules:",
            "",
            "WHAT TO IDENTIFY:",
            "- Visible structural elements ONLY (walls, columns, beams, slabs, doors, windows, stairs)",
            "- Materials clearly visible (concrete, steel, brick, glass, metal frames)",
            "- Construction stage and completion status",
            "- Each element's visible percentage (0-100%)",
            "",
            "ANTI-HALLUCINATION RULES:",
            "1. NEVER infer occluded, hidden, or internal parts",
            "2. NEVER assume materials you cannot see",
            "3. NEVER detect elements outside the image frame",
            "4. Use hedging: 'appears to be', 'likely', 'possibly', 'seems to'",
            "5. Rate confidence for EACH element (0.0-1.0 scale)",
            "6. Specify visible percentage honestly",
            "7. Note viewing limitations (angle, obstructions, lighting)",
            "",
            "IF UNCERTAIN:",
            "- Mark confidence < 0.5",
            "- State 'cannot determine from this angle'",
            "- List in analysis_limitations",
            ""
        ])
        
        # 5. Output Format
        prompt_parts.extend([
            "[OUTPUT FORMAT]",
            "Return structured description with:",
            "",
            "VIEWING CONDITIONS:",
            "- Angle: (frontal/lateral/aerial/oblique)",
            "- Lighting: (excellent/good/poor/backlit)",
            "- Clarity: (excellent/good/acceptable/poor)",
            "- Obstructions: list any (scaffolding, equipment, tarps)",
            "",
            "ELEMENTS DETECTED:",
            "For each visible element:",
            "- element_type: specific type",
            "- element_name: from BIM if identifiable",
            "- confidence: 0.0-1.0 (how certain you are)",
            "- status: completed/in_progress/not_started",
            "- description: what you observe",
            "- visible_percentage: 0-100% (how much is visible)",
            "- uncertainty_notes: any doubts or limitations",
            "",
            "CONSTRUCTION PHASE:",
            "- foundation/structure/finishing/completed",
            "",
            "OVERALL QUALITY:",
            "- excellent/good/acceptable/poor (based on visible work)",
            "",
            "VISIBLE ISSUES:",
            "- List any problems, defects, or deviations observed",
            "",
            "CONFIDENCE SCORE:",
            "- Overall analysis confidence (0.0-1.0)",
            "",
            "ANALYSIS LIMITATIONS:",
            "- What couldn't be assessed from this view",
            "- Required additional views/angles",
            "",
            "Be precise, technical, and honest about uncertainties."
        ])
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info(
            "advanced_prompt_built",
            has_rag=bool(rag_context),
            rag_count=len(rag_context) if rag_context else 0,
            has_temporal=bool(temporal_context),
            has_project=bool(project_context),
            prompt_length=len(final_prompt),
            sections=["BIM", "TEMPORAL", "PROJECT", "TASK", "FORMAT"]
        )
        
        return final_prompt

    async def _get_previous_analysis(self, project_id: str) -> dict | None:
        try:
            analyses = list(
                ConstructionAnalysisModel.project_id_index.query(project_id, scan_index_forward=False, limit=1)
            )

            if not analyses:
                return None

            a = analyses[0]
            return {
                "timestamp": a.analyzed_at,
                "overall_progress": float(a.overall_progress),
                "detected_elements": [self._parse_element(e) for e in (a.detected_elements or [])],
                "construction_phase": self._infer_phase(float(a.overall_progress)),
                "days_since": (datetime.now() - datetime.fromisoformat(a.analyzed_at.replace("Z", "+00:00"))).days
            }
        except Exception as e:
            logger.error("fetch_previous_error", error=str(e))
            return None

    def _parse_element(self, elem) -> dict:
        return (
            elem
            if isinstance(elem, dict)
            else {
                "element_name": elem.get("element_name") or elem.get("element_id"),
                "element_type": elem.get("element_type"),
                "status": elem.get("status"),
            }
        )

    def _infer_phase(self, progress: float) -> str:
        if progress < 25:
            return "foundation"
        if progress < 60:
            return "structure"
        if progress < 90:
            return "finishing"
        return "completed"

    def _build_temporal_context(self, prev: dict) -> str:
        days = self._calculate_days_since(prev)
        elements = prev.get("detected_elements", [])

        completed = [e for e in elements if e.get("status") == "completed"]
        in_progress = [e for e in elements if e.get("status") == "in_progress"]

        context = f"""PREVIOUS ANALYSIS ({days} days ago):
Progress: {prev.get("overall_progress")}% | Phase: {prev.get("construction_phase")}
"""

        if completed:
            context += "\nCOMPLETED: " + ", ".join([e.get("element_name", "?") for e in completed[:5]])
        if in_progress:
            context += "\nIN PROGRESS: " + ", ".join([e.get("element_name", "?") for e in in_progress[:5]])

        context += f"""\n\nFOCUS:
1. Verify IN PROGRESS elements are now COMPLETED
2. Identify NEW elements
3. Confirm COMPLETED elements remain completed
4. Expected progress: +{min(days * 2, 20):.0f}% based on {days} days
"""
        return context

    def _calculate_days_since(self, prev: dict) -> int:
        try:
            ts = prev.get("timestamp")
            prev_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            return (datetime.now() - prev_date).days if prev_date else 0
        except:
            return 0
