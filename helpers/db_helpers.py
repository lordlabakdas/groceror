from typing import Dict, List


class DBHelper(object):
    @staticmethod
    def convert_query_result_to_dict(query_result: List) -> List[Dict]:
        return [row.__dict__.pop("_sa_instance_state") for row in query_result]
