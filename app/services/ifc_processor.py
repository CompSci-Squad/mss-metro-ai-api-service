"""
Serviço simplificado de processamento de arquivos IFC usando IfcOpenShell.

Extração essencial e rápida de elementos BIM para análise.
"""

import asyncio
import tempfile
from datetime import datetime
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import structlog

from app.core.settings import settings

logger = structlog.get_logger(__name__)


class IFCProcessorService:
    """
    Serviço simplificado para extração essencial de elementos IFC.

    - Processamento paralelo sempre ativo
    - Filtros otimizados (sets O(1))
    - Sem validações de tamanho
    - Sem limites de elementos
    - Extração mínima e rápida
    """

    def __init__(self, embedding_service=None):
        """Inicializa o serviço."""
        self.embedding_service = embedding_service
        self.ignored_types_set: set[str] = set(settings.ifc_ignored_types)
        self.max_workers: int = settings.ifc_max_workers
        self.relevant_types = {
            "IfcWall",
            "IfcSlab",
            "IfcWindow",
            "IfcDoor",
            "IfcCurtainWall",
            "IfcMember",
            "IfcPlate",
            "IfcRailing",
            "IfcStair",
            "IfcStairFlight",
            "IfcCovering",
            "IfcBuildingElementProxy",
        }



        logger.info("ifc_processor_inicializado", ignored_types=len(self.ignored_types_set))

    def _visual_ifc_description(self, element: dict) -> str:
        """
        Descrição ultracurta para SigLIP.
        Mantém apenas tipo + descrição visual curta.
        Evita textos longos (SigLIP limita ~64 tokens).
        """

        etype = element.get("element_type", "Unknown")

        # Dicionário visual otimizado (baseado em capturas de imagem reais)
        visual_lookup = {
            "Wall": "vertical wall surface",
            "Slab": "flat concrete slab",
            "Floor": "flat horizontal floor",
            "Door": "rectangular door opening",
            "Window": "glass window frame",
            "Column": "vertical support column",
            "Beam": "horizontal support beam",
            "Stair": "stepped staircase",
            "Railing": "metal safety railing",
            "CurtainWall": "glass facade panel",
            "SystemPanel": "glass panel",
            "Member": "metal structural frame",
            "Plate": "flat metal plate",
            "BuildingElementPart": "component of larger element",
            "BuildingElementProxy": "geometric placeholder object",
        }

        visual_desc = visual_lookup.get(etype, f"{etype.lower()} element")

        # Texto final **curto**, estilo legenda do CLIP/SigLIP
        description = f"{etype} | {visual_desc}"

        # Garantia: nunca deixar ultrapassar limite (64 tokens > ~200 chars)
        return description[:200]


    async def process_ifc_file(self, file_content: bytes) -> dict[str, Any]:
        """Processa arquivo IFC e extrai elementos essenciais."""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ifc") as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            try:
                ifc_file = ifcopenshell.open(temp_path)
                project_info = await self._extract_project_info(ifc_file)
                elements = await self._extract_elements(ifc_file)

                if not elements:
                    raise ValueError("Nenhum elemento BIM encontrado")

                # Serializa para DynamoDB (SEM dedupe!)
                serialized_elements = [self._deep_serialize(elem) for elem in elements]

                return {
                    "project_info": project_info,
                    "total_elements": len(serialized_elements),
                    "elements": serialized_elements,
                    "processed_at": datetime.utcnow().isoformat(),
                }

            finally:
                import os

                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            logger.error("erro_processar_ifc", error=str(e))
            raise


    async def _extract_project_info(self, ifc_file) -> dict:
        try:
            projects = ifc_file.by_type("IfcProject")
            logger.info("projetos_encontrados", count=len(projects))

            if not projects:
                logger.warning("nenhum_projeto_ifc_encontrado")
                return {"project_name": "Undefined"}

            project = projects[0]
            site = ifc_file.by_type("IfcSite")
            building = ifc_file.by_type("IfcBuilding")

            logger.info("estrutura_ifc", sites=len(site), buildings=len(building))

            return {
                "project_name": project.Name if hasattr(project, "Name") else "Sem nome",
                "description": project.Description if hasattr(project, "Description") else None,
                "site_name": site[0].Name if site and hasattr(site[0], "Name") else None,
                "building_name": (building[0].Name if building and hasattr(building[0], "Name") else None),
            }

        except Exception as e:
            logger.warning("erro_extrair_info_projeto", error=str(e), exc_info=True)
            return {"project_name": "Undefined"}

    async def _extract_elements(self, ifc_file) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []

        all_products = ifc_file.by_type("IfcProduct", include_subtypes=True)

        tasks = []
        for item in all_products:
            etype = item.is_a()

            # FILTRO REAL: somente elementos estruturais / arquitetônicos
            if etype not in self.relevant_types:
                continue

            tasks.append(self._parse_element(item, etype))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict):
                elements.append(result)

        return elements


    async def _parse_element(self, ifc_element, element_type: str) -> dict | None:
        try:
            return {
                "element_id": getattr(ifc_element, "GlobalId", None),
                "element_type": element_type.replace("Ifc", ""),
                "name": getattr(ifc_element, "Name", None),
                "description": getattr(ifc_element, "Description", None),
                "object_type": getattr(ifc_element, "ObjectType", None),
                "properties": self._extract_properties(ifc_element),
                "spatial": self._extract_spatial_location(ifc_element),
                "materials": self._extract_materials(ifc_element),
            }
        except Exception:
            return None

    def _extract_properties(self, ifc_element) -> dict:
        properties = {}
        try:
            if hasattr(ifc_element, "IsDefinedBy"):
                for definition in ifc_element.IsDefinedBy:
                    if definition.is_a("IfcRelDefinesByProperties"):
                        property_set = definition.RelatingPropertyDefinition

                        if property_set.is_a("IfcPropertySet"):
                            for prop in property_set.HasProperties:
                                if prop.is_a("IfcPropertySingleValue"):
                                    prop_name = prop.Name
                                    prop_value = prop.NominalValue.wrappedValue if prop.NominalValue else None
                                    properties[prop_name] = self._serialize_value(prop_value)

            if hasattr(ifc_element, "Description") and ifc_element.Description:
                properties["Description"] = str(ifc_element.Description)

            if hasattr(ifc_element, "ObjectType") and ifc_element.ObjectType:
                properties["ObjectType"] = str(ifc_element.ObjectType)

        except Exception as e:
            logger.warning("erro_extrair_propriedades", error=str(e))

        return properties

    def _serialize_value(self, value):
        if value is None:
            return None
        if hasattr(value, "is_a"):
            return str(value)
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return str(value)

    def _extract_spatial_location(self, ifc_element) -> dict:
        spatial_data = {
            "storey": None,
            "storey_elevation": None,
            "container": None,
            "placement": None,
        }

        try:
            for rel in getattr(ifc_element, "ContainedInStructure", []):
                relating_structure = rel.RelatingStructure
                if relating_structure.is_a("IfcBuildingStorey"):
                    spatial_data["storey"] = relating_structure.Name
                    spatial_data["storey_elevation"] = getattr(relating_structure, "Elevation", None)
                else:
                    spatial_data["container"] = {
                        "type": relating_structure.is_a(),
                        "name": getattr(relating_structure, "Name", None),
                    }

            if hasattr(ifc_element, "ObjectPlacement") and ifc_element.ObjectPlacement:
                try:
                    matrix = ifcopenshell.util.placement.get_local_placement(ifc_element.ObjectPlacement)
                    if matrix is not None:
                        spatial_data["placement"] = {
                            "x": float(matrix[0][3]),
                            "y": float(matrix[1][3]),
                            "z": float(matrix[2][3]),
                        }
                except:
                    pass

        except Exception:
            pass

        return spatial_data

    def _extract_materials(self, ifc_element) -> list[str]:
        materials = []

        try:
            if hasattr(ifc_element, "HasAssociations"):
                for assoc in ifc_element.HasAssociations:
                    if assoc.is_a("IfcRelAssociatesMaterial"):
                        material_select = assoc.RelatingMaterial

                        if material_select.is_a("IfcMaterial"):
                            materials.append(material_select.Name)

                        elif material_select.is_a("IfcMaterialList"):
                            for mat in material_select.Materials:
                                materials.append(mat.Name)

                        elif material_select.is_a("IfcMaterialLayerSetUsage"):
                            layer_set = material_select.ForLayerSet
                            if layer_set and hasattr(layer_set, "MaterialLayers"):
                                for layer in layer_set.MaterialLayers:
                                    if layer.Material:
                                        materials.append(layer.Material.Name)

                        elif material_select.is_a("IfcMaterialProfileSetUsage"):
                            profile_set = material_select.ForProfileSet
                            if profile_set and hasattr(profile_set, "MaterialProfiles"):
                                for profile in profile_set.MaterialProfiles:
                                    if profile.Material:
                                        materials.append(profile.Material.Name)

        except Exception:
            pass

        return materials

    def _deep_serialize(self, obj):
        if obj is None:
            return None
        if hasattr(obj, "is_a"):
            return str(obj)
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {k: self._deep_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._deep_serialize(item) for item in obj]
        return str(obj)

    def _normalized_identity(self, elem):
        etype = (elem.get("element_type") or "").strip().lower()
        name = (elem.get("name") or "").strip().lower()
        return f"{etype}|{name}"

    def dedupe_elements(self, elements: list[dict]) -> list[dict]:
        seen = {}

        for elem in elements:
            key = self._normalized_identity(elem)

            # Inicializa lista de IDs
            if "element_ids_group" not in elem:
                elem["element_ids_group"] = []
            if elem.get("element_id"):
                elem["element_ids_group"].append(elem["element_id"])

            if key not in seen:
                seen[key] = elem
            else:
                old = seen[key]

                # Merge IDs
                merged = list(set(old["element_ids_group"] + elem["element_ids_group"]))
                old["element_ids_group"] = merged

        return list(seen.values())

    async def generate_embeddings_context(self, elements: list[dict]) -> list[str]:
        return [self._visual_ifc_description(elem) for elem in elements]

    async def index_elements_to_opensearch(self, project_id: str, description: str | None, elements: list[dict]) -> int:
        if not elements:
            raise ValueError("Não há elementos para indexar no OpenSearch")
        if not self.embedding_service:
            logger.warning("embedding_service_nao_configurado")
            return 0

        try:
            from app.models.opensearch import BIMElementEmbedding

            indexed_count = 0

            for element in elements:
                # Use descrição VISUAL ao invés de nome/props
                context = self._visual_ifc_description(element)

                embedding_vector = await self.embedding_service.generate_text_embedding(context)

                doc = BIMElementEmbedding(
                    element_id=element["element_id"],
                    project_id=project_id,
                    project_description=description or "",
                    element_type=element["element_type"],
                    description=context,
                    element_name=element.get("name", ""),
                    properties="",
                    embedding=embedding_vector,
                )
                doc.save()
                indexed_count += 1

            logger.info("elementos_indexados", count=indexed_count, project_id=project_id)
            return indexed_count

        except Exception as e:
            logger.error("erro_indexar_elementos", error=str(e), exc_info=True)
            return 0
