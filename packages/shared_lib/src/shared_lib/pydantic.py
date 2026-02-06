from pydantic import BaseModel


class APIBaseModel(BaseModel):
    def __str__(self):
        return self.model_dump_json(indent=2, ensure_ascii=False)
