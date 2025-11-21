"""IFC→Embedding→OpenSearch→RAG→VLM Evaluation Pipeline.

This script implements a full evaluation pipeline for BIM analysis:
1. IFC Ingestion: Read IFC file and extract structural elements
2. Embedding Generation: Generate embeddings for each element
3. OpenSearch Storage: Store embeddings in OpenSearch vector database
4. RAG Pipeline: Retrieve relevant elements for a given image query
5. VLM Prompt: Use Vision-Language Model to match elements with image
6. Output Handling: Parse JSON response and save evaluation results
"""

import asyncio
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler

# Add app to Python path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.settings import settings
from app.models.opensearch import BIMElementEmbedding, configure_opensearch
from app.services.embedding_service import EmbeddingService
from app.services.ifc_processor import IFCProcessorService
from app.services.rag_search_service import RAGSearchService


# ============================================================================
# DEDUPLICATION HELPERS
# ============================================================================


def build_normalized_identity(elem: dict[str, Any]) -> str:
    """
    Build a semantic key for an IFC element:
    element_type + name/element_name (lowercased + trimmed).
    """
    etype = (elem.get("element_type") or "").strip().lower()
    name = (elem.get("name") or elem.get("element_name") or "").strip().lower()
    return f"{etype}|{name}"


def dedupe_ifc_elements(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate IFC elements using semantic identity:
    element_type + normalized name.

    - Keeps ONE representative per semantic group
    - Aggregates all element_ids into 'element_ids_group'
    - For RAG results (with similarity_score), keeps the best-scoring representative
    """
    seen: dict[str, dict[str, Any]] = {}

    for elem in elements:
        semantic_key = build_normalized_identity(elem)
        elem_id = elem.get("element_id")

        # Ensure we always have a group list
        if "element_ids_group" not in elem:
            elem["element_ids_group"] = []
        if elem_id and elem_id not in elem["element_ids_group"]:
            elem["element_ids_group"].append(elem_id)

        if semantic_key not in seen:
            # First time we see this semantic key
            seen[semantic_key] = elem
        else:
            existing = seen[semantic_key]

            # Merge element_ids_group
            existing_group = set(existing.get("element_ids_group", []))
            new_group = set(elem.get("element_ids_group", []))
            merged = list(existing_group.union(new_group))
            existing["element_ids_group"] = merged

            # If there is similarity_score, keep the best representative
            new_score = elem.get("similarity_score")
            old_score = existing.get("similarity_score")

            if isinstance(new_score, (int, float)):
                if (not isinstance(old_score, (int, float))) or (new_score > old_score):
                    # Replace representative, but keep merged ids
                    elem["element_ids_group"] = merged
                    seen[semantic_key] = elem

    return list(seen.values())


# ============================================================================
# STEP 1: IFC INGESTION
# ============================================================================


async def ingest_ifc_file(ifc_file_path: str, project_id: str) -> dict:
    """
    Read IFC file and extract all structural elements.

    Args:
        ifc_file_path: Path to the IFC file
        project_id: Unique project identifier

    Returns:
        Dictionary with project info and extracted elements (deduplicated)
    """
    print(f"\n📁 STEP 1: IFC INGESTION")
    print(f"Reading IFC file: {ifc_file_path}")

    # Initialize services
    embedding_service = EmbeddingService()
    ifc_processor = IFCProcessorService(embedding_service=embedding_service)

    # Read IFC file
    with open(ifc_file_path, "rb") as f:
        ifc_content = f.read()

    # Process IFC file
    result = await ifc_processor.process_ifc_file(ifc_content)

    print(f"Project: {result['project_info']['project_name']}")
    print(f"Total elements extracted (raw): {result['total_elements']}")
    print(f"Element types: {set(e['element_type'] for e in result['elements'])}")

    print(f"Total elements after semantic dedupe: {result['total_elements']}")

    return result


# ============================================================================
# STEP 2: EMBEDDING GENERATION & OPENSEARCH STORAGE
# ============================================================================


async def generate_and_store_embeddings(
    project_id: str, project_description: str, elements: list[dict], embedding_service: EmbeddingService
) -> int:
    """
    Generate embeddings for each structural element and store in OpenSearch.

    Args:
        project_id: Unique project identifier
        project_description: Project description
        elements: List of IFC elements (already deduped)
        embedding_service: Embedding service instance

    Returns:
        Number of elements indexed
    """
    ifc_processor = IFCProcessorService(embedding_service=embedding_service)
    print(f"\nSTEP 2: EMBEDDING GENERATION & OPENSEARCH STORAGE")

    indexed_count = await ifc_processor.index_elements_to_opensearch(
        project_id=project_id, description=project_description, elements=elements
    )

    print(f"✓ Successfully indexed {indexed_count} elements in OpenSearch")
    return indexed_count


# ============================================================================
# STEP 3: RAG PIPELINE - RETRIEVE RELEVANT ELEMENTS
# ============================================================================


async def retrieve_relevant_elements(
    project_id: str, image_path: str, embedding_service: EmbeddingService, top_k: int = 10
) -> list[dict]:
    """
    Retrieve top-k most relevant IFC elements for the given image.

    Args:
        project_id: Unique project identifier
        image_path: Path to the image file
        embedding_service: Embedding service instance
        top_k: Number of elements to retrieve

    Returns:
        List of relevant elements with similarity scores (deduped)
    """
    print(f"\n🔍 STEP 3: RAG PIPELINE - RETRIEVE RELEVANT ELEMENTS")
    print(f"Analyzing image: {image_path}")

    # Read image
    with open(image_path, "rb") as f:
        image_data = f.read()

    # Generate image embedding
    image_embedding = await embedding_service.generate_image_embedding(image_data)
    print(len(image_embedding))

    if not image_embedding:
        print("⚠ Warning: Failed to generate image embedding")
        return []

    # Search in OpenSearch
    rag_service = RAGSearchService()
    context = await rag_service.fetch_rag_context(image_embedding=image_embedding, project_id=project_id, top_k=top_k)

    elements = context.get("elements", [])
    print(f"✓ Retrieved {len(elements)} raw elements from RAG")

    # DEDUPE RAG results by semantic identity (type + name)
    deduped_elements = dedupe_ifc_elements(elements)
    print(f"✓ After semantic dedupe (RAG): {len(deduped_elements)} unique elements")

    for i, elem in enumerate(deduped_elements[:5], 1):  # Show first 5
        print(
            f"  {i}. {elem['element_type']} - "
            f"{elem.get('element_name') or elem.get('name', 'N/A')} "
            f"(score: {elem.get('similarity_score', 'N/A')})"
        )

    return deduped_elements


# ============================================================================
# STEP 4: VLM PROMPT FORMATTING
# ============================================================================


def format_vlm_prompt(ifc_elements: list[dict]) -> str:
    """
    Formata prompt para VLM com:
      - Anti-alucinação agressiva
      - Deduplicação via normalized_identity
      - Heurísticas específicas para elementos IFC
      - Structured Output rigoroso com JSON Schema
      - Instruções imutáveis para classificação
    """

    # Prepara contexto IFC com chave de normalização
    ifc_context = "\n".join(
        [
            f"- element_id: {e['element_id']}\n"
            f"  type: {e['element_type']}\n"
            f"  name: {e.get('element_name', 'N/A') or e.get('name', 'N/A')}\n"
            f"  normalized_identity: {build_normalized_identity(e)}"
            for e in ifc_elements
        ]
    )

    # JSON schema (EXTREMAMENTE RIGOROSO)
    json_schema = """
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "normalized_identity": { "type": "string" },
          "element_ids": {
            "type": "array",
            "items": { "type": "string" }
          },
          "classification": {
            "type": "string",
            "enum": ["visible", "not_visible", "undetermined"]
          },
          "visual_explanation": { "type": "string" }
        },
        "required": [
          "normalized_identity",
          "element_ids",
          "classification",
          "visual_explanation"
        ]
      }
    }
  },
  "required": ["results"]
}
"""

    # HEURÍSTICAS BIM → VISÃO
    heuristics = """
### HEURISTIC RULES (DO NOT BREAK)

You MUST apply these domain heuristics when judging visibility:

1. **Floors / Slabs / Pavements**
   - Usually horizontal surfaces under people's feet.
   - Only classify as visible if a large flat horizontal plane is clearly visible.
   - If uncertain → "undetermined".

2. **Walls / Vertical Surfaces**
   - Must appear clearly as structural vertical planes.
   - Texture repetition or pattern does NOT guarantee it's a wall.
   - If the camera angle hides the wall → "undetermined".

3. **Beams / Columns**
   - Columns are vertical load elements with clear thickness.
   - Beams are horizontal structural bars.
   - If only shadows or partial shapes appear → "undetermined".

4. **Doors / Windows**
   - Only classify as visible if:
       - The frame outline is clearly visible AND
       - It matches the general geometry of the element.
   - If uncertain or ambiguous → "undetermined".

5. **Stairs / Ramps**
   - Must show visible steps or sloped surfaces.
   - If only the top or shadow is visible → "undetermined".

6. **BuildingElementPart / Proxies**
   - These frequently represent small subdivisions of a bigger element.
   - Treat parts with identical normalized_identity as one real object.
   - Never classify multiple parts separately.

7. **Anti-hallucination override**
   - If the image does NOT clearly show the shape: → "undetermined".
   - Lack of evidence ≠ negative evidence.
"""

    # MODO ULTRA ANTI-ALUCINAÇÃO
    anti_hallucination = """
### ULTRA ANTI-HALLUCINATION MODE (MANDATORY)

- You MUST NOT infer anything not clearly visible in the image.
- If ANY detail of the element is not unambiguously observable → classify "undetermined".
- Do NOT guess.
- Do NOT fill gaps.
- Do NOT use prior world knowledge.
- Ignore typical construction patterns; rely ONLY on pixels.
- If the element name suggests something that you cannot see → "undetermined".
- If multiple interpretations are possible → "undetermined".
- Even if the image likely contains the element, but not clearly → "undetermined".
- Absence of evidence ≠ evidence of absence.
"""

    # PROMPT FINAL
    prompt = f"""
STRUCTURE VISUAL MATCH MODE — DEDUPED + ULTRA ANTI-HALLUCINATION

You will analyze an image and determine whether IFC elements are visible.

You receive a list of IFC elements extracted via RAG.  
Different element_ids may represent the SAME real-world object.  
Use the provided `normalized_identity` field to merge duplicates.

### IFC ELEMENTS (dedupe using normalized_identity):
{ifc_context}

{heuristics}

{anti_hallucination}

### YOUR TASKS:

1. **Group elements by normalized_identity**
   Example:
     - If 12 elements share "slab|floor:ed-021" → treat them as ONE object.

2. **For each grouped object**, determine strictly using the image whether it is:
   - "visible"
   - "not_visible"
   - "undetermined"

3. **Never classify based on IFC metadata alone.**
   ONLY use the visual content of the image.

4. **If unsure at all → "undetermined".**

5. **Output MUST respect the JSON schema EXACTLY.**
   No explanations outside JSON. No additional fields.

### STRICT JSON SCHEMA (MANDATORY – DO NOT BREAK):
{json_schema}

### OUTPUT:
Return ONLY a JSON object matching the schema above. Nothing else.
"""

    return prompt


# ============================================================================
# STEP 5: VLM INFERENCE
# ============================================================================


# def initialize_vlm() -> Llama:
#     """
#     Initialize the Vision-Language Model (LLaVA).

#     Returns:
#         Initialized Llama model instance
#     """
#     print(f"\nInitializing Vision-Language Model (LLaVA)...")

#     chat_handler = Llava15ChatHandler(clip_model_path="./models/llava-v1.5/mmproj-model-f16.gguf")

#     llm = Llama(
#         model_path="./models/llava-v1.5/ggml-model-q4_k.gguf",
#         chat_handler=chat_handler,
#         use_mmap=True,
#         n_threads=os.cpu_count(),
#         n_batch=512,
#         use_mlock=False,
#         verbose=False,
#         n_ctx=8192,
#     )

#     print(f"VLM initialized successfully")
#     return llm


# def image_to_base64_data_uri(file_path: str) -> str:
#     """
#     Convert image file to base64 data URI.

#     Args:
#         file_path: Path to image file

#     Returns:
#         Base64 encoded data URI
#     """
#     with open(file_path, "rb") as img_file:
#         base64_data = base64.b64encode(img_file.read()).decode("utf-8")
#         return f"data:image/png;base64,{base64_data}"

from openai import OpenAI

def encode_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def run_vlm_inference_openai(image_path: str, prompt: str) -> dict:
    print("\nSTEP 4: VLM INFERENCE (OpenAI GPT-4.1 Vision)")
    
    base64_image = encode_image_base64(image_path)
    client = OpenAI(api_key=)

    response = client.responses.create(
        model="gpt-4.1",          # modelo multimodal da OpenAI
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}",
                    },
                ],
            }
        ],
    )

    # openai returns structured fields
    return {
        "text": response.output_text,
        "raw": response
    }

# ============================================================================
# STEP 6: OUTPUT HANDLING & EVALUATION
# ============================================================================


def parse_vlm_response(vlm_output: dict) -> dict:
    """
    Parse VLM response and extract JSON results.

    Args:
        vlm_output: Raw VLM output dictionary

    Returns:
        Parsed results dictionary
    """
    print(f"\nSTEP 5: OUTPUT HANDLING")

    try:
        # Extract text response
        response_text = vlm_output["text"]
        print(f"Raw response length: {len(response_text)} characters")

        # Try to extract JSON from response
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1

        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            results = json.loads(json_str)
            print(f"Successfully parsed JSON response")
            return results
        else:
            print(f"Warning: No JSON found in response")
            return {"error": "No JSON found", "raw_response": response_text}

    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON: {e}")
        return {"error": str(e), "raw_response": response_text}
    except Exception as e:
        print(f"Warning: Error parsing response: {e}")
        return {"error": str(e), "raw_output": vlm_output}


def save_evaluation_results(results: dict, output_path: str = "./output/evaluation_results.json") -> None:
    """
    Save evaluation results to a JSON file.

    Args:
        results: Evaluation results dictionary
        output_path: Path to save the results
    """
    # Create output directory if it doesn't exist
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Add metadata
    results["metadata"] = {
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0",
    }

    # Save to file
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")


def print_evaluation_summary(results: dict) -> None:
    """
    Print a summary of the evaluation results.

    Args:
        results: Parsed evaluation results
    """
    print(f"\n" + "=" * 70)
    print(f"EVALUATION SUMMARY")
    print(f"=" * 70)

    if "error" in results:
        print(f"\nError: {results['error']}")
        if "raw_response" in results:
            print(f"\nRaw response:\n{results['raw_response'][:500]}...")
        return

    if "results" in results:
        element_results = results["results"]
        print(f"\nTotal grouped elements evaluated: {len(element_results)}")

        # Count classifications
        visible = sum(1 for r in element_results if r.get("classification") == "visible")
        not_visible = sum(1 for r in element_results if r.get("classification") == "not_visible")
        undetermined = sum(1 for r in element_results if r.get("classification") == "undetermined")

        print(f"\nClassification breakdown:")
        print(f"  Visible: {visible}")
        print(f"  Not visible: {not_visible}")
        print(f"  Undetermined: {undetermined}")

        print(f"\nDetailed results:")
        for i, result in enumerate(element_results, 1):
            norm_id = result.get("normalized_identity", "N/A")
            elem_ids = result.get("element_ids", [])
            classification = result.get("classification", "N/A")
            explanation = result.get("visual_explanation", "N/A")

            icon = "✓" if classification == "visible" else ("✗" if classification == "not_visible" else "?")
            print(f"\n{i}. {icon} Normalized identity: {norm_id}")
            print(f"   Element IDs: {', '.join(elem_ids) if elem_ids else 'N/A'}")
            print(f"   Classification: {classification}")
            if isinstance(explanation, str) and len(explanation) > 100:
                print(f"   Explanation: {explanation[:100]}...")
            else:
                print(f"   Explanation: {explanation}")

    print(f"\n" + "=" * 70)


# ============================================================================
# MAIN PIPELINE
# ============================================================================


async def run_full_pipeline(
    ifc_file_path: str,
    image_path: str,
    project_id: str,
    top_k: int = 10,
    output_path: str = "./output/evaluation_results.json",
):
    """
    Run the complete IFC→Embedding→OpenSearch→RAG→VLM evaluation pipeline.

    Args:
        ifc_file_path: Path to IFC file
        image_path: Path to image for evaluation
        project_id: Unique project identifier
        top_k: Number of elements to retrieve via RAG
        output_path: Path to save evaluation results

    Returns:
        Complete evaluation results
    """
    print("\n" + "=" * 70)
    print("IFC→EMBEDDING→OPENSEARCH→RAG→VLM EVALUATION PIPELINE")
    print("=" * 70)

    try:
        # Initialize OpenSearch connection
        print(f"Initializing OpenSearch connection...")
        configure_opensearch(
            hosts=[f"{settings.opensearch_host}:{settings.opensearch_port}"],
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=settings.opensearch_verify_certs,
        )
        print(f"OpenSearch connected")

        # STEP 1: IFC Ingestion (with dedupe)
        #ifc_data = await ingest_ifc_file(ifc_file_path, project_id)

        # STEP 2: Generate Embeddings & Store in OpenSearch
        embedding_service = EmbeddingService()
        # indexed_count = await generate_and_store_embeddings(
        #     project_id=project_id,
        #     project_description=ifc_data["project_info"]["project_name"],
        #     elements=ifc_data["elements"],
        #     embedding_service=embedding_service
        # )

        # STEP 3: RAG - Retrieve Relevant Elements (with dedupe)
        relevant_elements = await retrieve_relevant_elements(
            project_id=project_id, image_path=image_path, embedding_service=embedding_service, top_k=top_k
        )

        if not relevant_elements:
            print("Warning: No relevant elements found")
            return {"error": "No relevant elements found"}

        # STEP 4: Format VLM Prompt
        prompt = format_vlm_prompt(relevant_elements)
        print(prompt)

        vlm_output = await run_vlm_inference_openai(image_path, prompt)

        # STEP 6: Parse and Save Results
        results = parse_vlm_response(vlm_output)

        # # Add context to results
        # results["pipeline_info"] = {
        #     "ifc_file": ifc_file_path,
        #     "image_file": image_path,
        #     "project_id": project_id,
        #     "total_ifc_elements": ifc_data["total_elements"],
        #     "indexed_elements": indexed_count,
        #     "rag_retrieved_elements": len(relevant_elements),
        #     "top_k": top_k,
        # }

        save_evaluation_results(results, output_path)
        print_evaluation_summary(results)

        return results

    except Exception as e:
        print(f"\nPipeline error: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":
    # Configuration
    IFC_FILE = "./data/MB-1.04.04.00-6B3-1001-1_v32.ifc"
    IMAGE_FILE = "./data/gustavo_fachada_atual.png"
    PROJECT_ID = "test_project_001"
    TOP_K = 50
    OUTPUT_FILE = "./output/evaluation_results.json"

    # Run pipeline
    results = asyncio.run(
        run_full_pipeline(
            ifc_file_path=IFC_FILE, image_path=IMAGE_FILE, project_id=PROJECT_ID, top_k=TOP_K, output_path=OUTPUT_FILE
        )
    )

    print(f"\nPipeline completed successfully!")
