import copy

from core.resource.arknightsGameData import ArknightsGameData, ArknightsGameDataResource
from core.util import integer, snake_case_to_pascal_case

from .operatorSearch import OperatorSearchInfo


class OperatorData:
    @classmethod
    async def get_operator_detail(cls, info: OperatorSearchInfo):
        operators = ArknightsGameData.operators

        if not info.name or info.name not in operators:
            return None, None

        operator = operators[info.name]

        real_name = await ArknightsGameData.get_real_name(operator.origin_name)

        detail, trust = operator.detail()
        modules = operator.modules()

        module_attr = {}
        if modules:
            module = modules[-1]
            if module['detail']:
                attrs = module['detail']['phases'][-1]['attributeBlackboard']
                for attr in attrs:
                    module_attr[snake_case_to_pascal_case(attr['key'])] = integer(attr['value'])

        skills, skills_id, skills_cost, skills_desc = operator.skills()
        skins = operator.skins()

        operator_info = {
            'info': {
                'id': operator.id,
                'cv': operator.cv,
                'type': operator.type,
                'tags': operator.tags,
                'range': operator.range,
                'rarity': operator.rarity,
                'number': operator.number,
                'name': operator.name,
                'en_name': operator.en_name,
                'real_name': real_name,
                'wiki_name': operator.wiki_name,
                'index_name': operator.index_name,
                'origin_name': operator.origin_name,
                'classes': operator.classes,
                'classes_sub': operator.classes_sub,
                'classes_code': operator.classes_code,
                'race': operator.race,
                'drawer': operator.drawer,
                'team': operator.team,
                'group': operator.group,
                'nation': operator.nation,
                'birthday': operator.birthday,
                'profile': operator.profile,
                'impression': operator.impression,
                'limit': operator.limit,
                'unavailable': operator.unavailable,
                'potential_item': operator.potential_item,
                'is_recruit': operator.is_recruit,
                'is_sp': operator.is_sp
            },
            'skin': (await ArknightsGameDataResource.get_skin_file(skins[0], encode_url=True)) if skins else '',
            'trust': trust,
            'detail': detail,
            'modules': module_attr,
            'talents': operator.talents(),
            'potential': operator.potential(),
            'building_skills': operator.building_skills(),
            'skill_list': skills,
            'skills_cost': skills_cost,
            'skills_desc': skills_desc
        }
        tokens = {
            'id': operator.id,
            'name': operator.name,
            'tokens': operator.tokens()
        }

        return operator_info, tokens

    @classmethod
    async def get_level_up_cost(cls, info: OperatorSearchInfo):
        operators = ArknightsGameData.operators
        materials = ArknightsGameData.materials

        if not info.name or info.name not in operators:
            return None

        operator = operators[info.name]
        evolve_costs = operator.evolve_costs()

        evolve_costs_list = {}
        for item in evolve_costs:
            material = materials[item['use_material_id']]

            if item['evolve_level'] not in evolve_costs_list:
                evolve_costs_list[item['evolve_level']] = []

            evolve_costs_list[item['evolve_level']].append({
                'material_name': material['material_name'],
                'material_icon': material['material_icon'],
                'use_number': item['use_number']
            })

        skills, skills_id, skills_cost, skills_desc = operator.skills()

        skills_cost_list = {}
        for item in skills_cost:
            material = materials[item['use_material_id']]
            skill_no = item['skill_no'] or 'common'

            if skill_no and skill_no not in skills_cost_list:
                skills_cost_list[skill_no] = {}

            if item['level'] not in skills_cost_list[skill_no]:
                skills_cost_list[skill_no][item['level']] = []

            skills_cost_list[skill_no][item['level']].append({
                'material_name': material['material_name'],
                'material_icon': material['material_icon'],
                'use_number': item['use_number']
            })

        skins = operator.skins()
        skin = ''
        if skins:
            skin = await ArknightsGameDataResource.get_skin_file(
                skins[1] if len(skins) > 1 else skins[0],
                encode_url=True
            )

        return {
            'skin': skin,
            'evolve_costs': evolve_costs_list,
            'skills': skills,
            'skills_cost': skills_cost_list
        }

    @classmethod
    async def get_skills_detail(cls, info: OperatorSearchInfo):
        operators = ArknightsGameData.operators

        if not info.name or info.name not in operators:
            return None

        operator = operators[info.name]
        skills, skills_id, skills_cost, skills_desc = operator.skills()

        return {
            'skills': skills,
            'skills_desc': skills_desc
        }

    @classmethod
    def find_operator_module(cls, info: OperatorSearchInfo, is_story: bool):
        operators = ArknightsGameData.operators
        materials = ArknightsGameData.materials

        operator = operators[info.name]
        modules = copy.deepcopy(operator.modules())

        if not modules:
            return None

        if is_story:
            return cls.find_operator_module_story(info.name, modules)

        def parse_trait_data(data):
            if data is None:
                return
            for candidate in data:
                blackboard = candidate['blackboard']
                if candidate['additionalDescription']:
                    candidate['additionalDescription'] = ArknightsGameDataResource.parse_template(
                        blackboard,
                        candidate['additionalDescription']
                    )
                if candidate['overrideDescripton']:
                    candidate['overrideDescripton'] = ArknightsGameDataResource.parse_template(
                        blackboard,
                        candidate['overrideDescripton']
                    )

        def parse_talent_data(data):
            if data is None:
                return
            for candidate in data:
                blackboard = candidate['blackboard']
                if candidate['upgradeDescription']:
                    candidate['upgradeDescription'] = ArknightsGameDataResource.parse_template(
                        blackboard,
                        candidate['upgradeDescription']
                    )

        for item in modules:
            if item['itemCost']:
                for lvl, item_cost in item['itemCost'].items():
                    for i, cost in enumerate(item_cost):
                        material = materials[cost['id']]
                        item_cost[i] = {
                            **cost,
                            'info': material
                        }

            if item['detail']:
                for stage in item['detail']['phases']:
                    for part in stage['parts']:
                        parse_trait_data(part['overrideTraitDataBundle']['candidates'])
                        parse_talent_data(part['addOrOverrideTalentDataBundle']['candidates'])

        return modules

    @staticmethod
    def find_operator_module_story(name, modules):
        text = f'博士，为您找到干员{name}的模组故事'

        for item in modules:
            text += '\n\n【%s】\n\n' % item['uniEquipName']
            text += item['uniEquipDesc']

        return text
