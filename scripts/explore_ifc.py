"""
Script para explorar e listar TUDO dentro de um arquivo IFC.
Versão: detalhada com foco em IfcBuildingElementProxy + extrações adicionais.

Uso:
    python scripts/explore_ifc_detalhado.py [caminho_para_arquivo.ifc]
"""

import sys
from pathlib import Path
from collections import defaultdict
import ifcopenshell
import ifcopenshell.util.placement
import json

def print_section(title: str, char: str = "="):
    print(f"\n{char * 80}")
    print(f"{title}")
    print(f"{char * 80}\n")

def explore_project_structure(ifc_file):
    print_section("📐 ESTRUTURA DO PROJETO")
    projects = ifc_file.by_type("IfcProject")
    print(f"Projetos encontrados: {len(projects)}")
    for project in projects:
        print(f"  - Nome: {getattr(project, 'Name', 'N/A')}")
        print(f"    Description: {getattr(project, 'Description', 'N/A')}")
        print(f"    GlobalId: {getattr(project, 'GlobalId', 'N/A')}")
    sites = ifc_file.by_type("IfcSite")
    print(f"\nSites encontrados: {len(sites)}")
    for site in sites:
        print(f"  - Nome: {getattr(site, 'Name', 'N/A')}")
        print(f"    RefLatitude: {getattr(site, 'RefLatitude', 'N/A')}")
        print(f"    RefLongitude: {getattr(site, 'RefLongitude', 'N/A')}")
    buildings = ifc_file.by_type("IfcBuilding")
    print(f"\nEdifícios encontrados: {len(buildings)}")
    for b in buildings:
        print(f"  - Nome: {getattr(b, 'Name', 'N/A')}")
        print(f"    Description: {getattr(b, 'Description', 'N/A')}")
    storeys = ifc_file.by_type("IfcBuildingStorey")
    print(f"\nAndares/Storeys encontrados: {len(storeys)}")
    for s in storeys:
        print(f"  - Nome: {getattr(s, 'Name', 'N/A')}")
        print(f"    Elevation: {getattr(s, 'Elevation', 'N/A')}")
        print(f"    GlobalId: {getattr(s, 'GlobalId', 'N/A')}")
    spaces = ifc_file.by_type("IfcSpace")
    print(f"\nEspaços encontrados: {len(spaces)}")
    if len(spaces) <= 10:
        for sp in spaces:
            print(f"  - Nome: {getattr(sp, 'Name', 'N/A')}")
    else:
        print(f"  (Mostrando apenas primeiros 10 de {len(spaces)})")
        for sp in spaces[:10]:
            print(f"  - Nome: {getattr(sp, 'Name', 'N/A')}")

def list_all_ifc_types(ifc_file):
    print_section("📋 TODOS OS TIPOS IFC PRESENTES")
    all_entities = ifc_file.by_type("IfcRoot")
    type_counts = defaultdict(int)
    for e in all_entities:
        type_counts[e.is_a()] += 1
    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    print(f"Total de tipos IFC diferentes: {len(sorted_types)}")
    print(f"Total de entidades: {sum(type_counts.values())}\n")
    print(f"{'Tipo IFC':<50} {'Quantidade':>10}")
    print("-" * 62)
    for t, c in sorted_types:
        print(f"{t:<50} {c:>10}")
    return sorted_types

def explore_building_element_proxies(ifc_file, max_examples: int = 5):
    print_section("🏗️ ELEMENTOS IfcBuildingElementProxy")
    proxies = ifc_file.by_type("IfcBuildingElementProxy")
    print(f"Total de IfcBuildingElementProxy: {len(proxies)}")
    for idx, p in enumerate(proxies[:max_examples], 1):
        # localização aproximada
        placement = None
        if hasattr(p, 'ObjectPlacement') and p.ObjectPlacement:
            try:
                matrix = ifcopenshell.util.placement.get_local_placement(p.ObjectPlacement)
                placement = {
                    "x": float(matrix[0][3]),
                    "y": float(matrix[1][3]),
                    "z": float(matrix[2][3]),
                }
            except:
                placement = None
        print(f"\n  Exemplo {idx}:")
        print(f"    GlobalId: {getattr(p, 'GlobalId', 'N/A')}")
        print(f"    Name: {getattr(p, 'Name', 'N/A')}")
        print(f"    ObjectType: {getattr(p, 'ObjectType', 'N/A')}")
        print(f"    HasRepresentation: {bool(getattr(p, 'Representation', None))}")
        print(f"    Placement: {placement}")

def explore_element_details(ifc_file, ifc_type: str, max_examples: int = 3):
    elements = ifc_file.by_type(ifc_type)
    if not elements:
        return
    print_section(f"Tipo: {ifc_type} (Total: {len(elements)})")
    print(f"Mostrando {min(max_examples, len(elements))} exemplos:")
    print("-" * 80)
    for idx, e in enumerate(elements[:max_examples], 1):
        print(f"\n  Exemplo {idx}:")
        print(f"    GlobalId: {getattr(e, 'GlobalId', 'N/A')}")
        print(f"    Name: {getattr(e, 'Name', 'N/A')}")
        print(f"    Description: {getattr(e, 'Description', 'N/A')}")
        print(f"    ObjectType: {getattr(e, 'ObjectType', 'N/A')}")
        has_repr = hasattr(e, 'Representation') and e.Representation
        print(f"    HasRepresentation: {has_repr}")
        has_place = hasattr(e, 'ObjectPlacement') and e.ObjectPlacement
        print(f"    HasPlacement: {has_place}")
        attrs = [a for a in dir(e) if not a.startswith('_') and a[0].isupper()]
        print(f"    Atributos IFC visíveis: {', '.join(attrs[:15])}")
        if len(attrs) > 15:
            print(f"      ... e mais {len(attrs)-15} atributos")

def explore_properties(ifc_file, ifc_type: str, max_examples: int = 2):
    elements = ifc_file.by_type(ifc_type)
    if not elements:
        return
    print(f"\n  📦 Propriedades (Property Sets) de {ifc_type}:")
    for idx, e in enumerate(elements[:max_examples], 1):
        print(f"\n    Elemento {idx} ({getattr(e, 'Name', 'N/A')}):")
        if hasattr(e, 'IsDefinedBy'):
            for d in e.IsDefinedBy:
                if d.is_a('IfcRelDefinesByProperties'):
                    ps = d.RelatingPropertyDefinition
                    if ps.is_a('IfcPropertySet'):
                        print(f"      Property Set: {ps.Name}")
                        for prop in ps.HasProperties[:5]:
                            if prop.is_a('IfcPropertySingleValue'):
                                val = prop.NominalValue.wrappedValue if prop.NominalValue else None
                                print(f"        - {prop.Name}: {val}")
                        if len(ps.HasProperties) > 5:
                            print(f"        ... e mais {len(ps.HasProperties)-5} propriedades")

def explore_relationships(ifc_file):
    print_section("🔗 RELACIONAMENTOS IFC")
    types = [
        "IfcRelContainedInSpatialStructure",
        "IfcRelAggregates",
        "IfcRelAssociatesMaterial",
        "IfcRelDefinesByProperties",
        "IfcRelDefinesByType",
        "IfcRelVoidsElement",
        "IfcRelFillsElement",
        "IfcRelConnectsElements",
    ]
    for t in types:
        rels = ifc_file.by_type(t)
        print(f"{t}: {len(rels)} relacionamentos")
        if rels and len(rels) <= 3:
            for r in rels[:2]:
                print(f"  Exemplo: {r}")

def explore_materials(ifc_file):
    print_section("🎨 MATERIAIS")
    mats = ifc_file.by_type("IfcMaterial")
    print(f"Total de materiais definidos: {len(mats)}")
    for m in mats[:20]:
        print(f"  - {m.Name}")
    if len(mats) > 20:
        print(f"  ... e mais {len(mats)-20} materiais")
    layers = ifc_file.by_type("IfcMaterialLayerSet")
    print(f"\nMaterial Layer Sets: {len(layers)}")
    profiles = ifc_file.by_type("IfcMaterialProfileSet")
    print(f"Material Profile Sets: {len(profiles)}")

def explore_geometry(ifc_file):
    print_section("📐 GEOMETRIA")
    repr_types = ["IfcShapeRepresentation", "IfcProductDefinitionShape", "IfcGeometricRepresentationContext"]
    for rt in repr_types:
        items = ifc_file.by_type(rt)
        print(f"{rt}: {len(items)}")
    geom_types = ["IfcExtrudedAreaSolid", "IfcFacetedBrep", "IfcPolyline", "IfcCartesianPoint", "IfcDirection"]
    print("\nPrimitivas Geométricas:")
    for gt in geom_types:
        items = ifc_file.by_type(gt)
        print(f"  {gt}: {len(items)}")

def explore_quantities(ifc_file):
    print_section("📊 QUANTIDADES")
    qts = ifc_file.by_type("IfcElementQuantity")
    print(f"Element Quantities encontrados: {len(qts)}")
    if qts:
        qty = qts[0]
        print(f"Exemplo: {qty.Name}")
        if hasattr(qty, 'Quantities'):
            for q in qty.Quantities[:5]:
                print(f"  - {q.is_a()}: {getattr(q, 'Name', 'N/A')}")

def explore_types(ifc_file):
    print_section("🏗️ TIPOS DE ELEMENTOS (IfcTypeObject)")
    types = ifc_file.by_type("IfcTypeObject")
    counts = defaultdict(int)
    for t in types:
        counts[t.is_a()] += 1
    print(f"Total de tipos de elementos: {len(types)}")
    for t, c in sorted(counts.items()):
        print(f"  {t}: {c}")

def explore_classifications(ifc_file):
    print_section("🏷️ CLASSIFICAÇÕES")
    cls = ifc_file.by_type("IfcClassification")
    print(f"Sistemas de classificação: {len(cls)}")
    for c in cls:
        print(f"  - {c.Name}")
        print(f"    Source: {getattr(c, 'Source', 'N/A')}")
        print(f"    Edition: {getattr(c, 'Edition', 'N/A')}")

def explore_units(ifc_file):
    print_section("📏 UNIDADES DE MEDIDA")
    uas = ifc_file.by_type("IfcUnitAssignment")
    for ua in uas:
        print("Unidades definidas:")
        for u in ua.Units:
            if hasattr(u, 'UnitType'):
                print(f"  - {u.UnitType}: {u}")

def full_exploration(ifc_file_path: str, save_report: bool = False, report_path: str = None):
    print_section(f"🔍 EXPLORAÇÃO COMPLETA DO ARQUIVO IFC: {ifc_file_path}", "█")
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        print(f"✓ Arquivo IFC aberto com sucesso")
        print(f"  Schema: {ifc_file.schema}")
    except Exception as e:
        print(f"❌ Erro ao abrir arquivo: {e}")
        return

    explore_project_structure(ifc_file)
    types = list_all_ifc_types(ifc_file)
    explore_building_element_proxies(ifc_file, max_examples=5)

    print_section("🏗️ DETALHES DE ELEMENTOS ESTRUTURAIS")
    structural_types = ["IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcColumn", 
                        "IfcBeam", "IfcDoor", "IfcWindow", "IfcRoof", "IfcStair"]
    for t in structural_types:
        explore_element_details(ifc_file, t, max_examples=2)
        explore_properties(ifc_file, t, max_examples=1)

    print_section("🔧 OUTROS ELEMENTOS")
    other_types = ["IfcCurtainWall", "IfcRailing", "IfcFooting", "IfcPile"]
    for t in other_types:
        explore_element_details(ifc_file, t, max_examples=1)

    explore_relationships(ifc_file)
    explore_materials(ifc_file)
    explore_geometry(ifc_file)
    explore_quantities(ifc_file)
    explore_types(ifc_file)
    explore_classifications(ifc_file)
    explore_units(ifc_file)

    print_section("📈 RESUMO ESTATÍSTICO", "█")
    total_entities = sum(count for _, count in types)
    print(f"Total de entidades no arquivo: {total_entities}")
    print(f"Total de tipos IFC diferentes: {len(types)}")
    print("\nTop 10 tipos mais comuns:")
    for idx, (t, c) in enumerate(types[:10], 1):
        percentage = (c / total_entities) * 100 if total_entities else 0
        print(f"  {idx}. {t}: {c} ({percentage:.1f}%)")

    if save_report and report_path:
        report = {
            "file": ifc_file_path,
            "schema": ifc_file.schema,
            "types": types,
            "proxies_count": len(ifc_file.by_type("IfcBuildingElementProxy")),
        }
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"\nRelatório salvo em: {report_path}")

def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/explore_ifc_detalhado.py <caminho_para_arquivo.ifc>")
        sys.exit(1)
    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"❌ Arquivo não encontrado: {file_path}")
        sys.exit(1)
    # Exemplo de salvar relatório se quiser
    # full_exploration(file_path, save_report=True, report_path="ifc_report.json")
    full_exploration(file_path)

if __name__ == "__main__":
    main()
