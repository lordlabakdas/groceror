from data_models.entity.owner import Owner
from data_models.db import db_session


class OwnerRegistration(object):

    def register_owner(self, new_owner_information):
        new_owner = Owner(
            email=new_owner_information["email"],
            phone=new_owner_information["phone"],
            username=new_owner_information["username"],
            password=new_owner_information["password"],
            first_name=None if "first_name" not in new_owner_information else new_owner_information[
                "first_name"],
            last_name=None if "first_name" not in new_owner_information else new_owner_information[
                "first_name"],
        )
        db_session.add(new_owner)
        db_session.commit()
        db_session.close()
