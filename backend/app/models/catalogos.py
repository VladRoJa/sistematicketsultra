#app\models\catalogos.py


from .. extensions import db

class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)

class Marca(db.Model):
    __tablename__ = 'marcas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)

class UnidadMedida(db.Model):
    __tablename__ = 'unidades_medida'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    abreviatura = db.Column(db.String(10), unique=True, nullable=True)

class GrupoMuscular(db.Model):
    __tablename__ = 'grupos_musculares'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)

class TipoInventario(db.Model):
    __tablename__ = 'tipos_inventario'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

class CatalogoClasificacion(db.Model):
    __tablename__ = 'catalogo_clasificacion'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('catalogo_clasificacion.id'), nullable=True)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=False)
    nivel = db.Column(db.Integer, nullable=False, default=1)
    
    # Relaciones
    hijos = db.relationship(
        'CatalogoClasificacion',
        backref=db.backref('padre', remote_side=[id]),
        cascade='all, delete-orphan'
    )
    departamento = db.relationship('Departamento', backref='clasificaciones')