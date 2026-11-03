-- Tipo de hóspede (sócio do clube ou convidado) e valor da diária. Os dois são opcionais (NULL = não informado):
-- reservas antigas e importadas ficam como estão. O valor é guardado em CENTAVOS (inteiro), nunca em decimal.
ALTER TABLE reservas ADD COLUMN tipo TEXT CHECK (tipo IN ('socio','convidado'));
ALTER TABLE reservas ADD COLUMN diaria_centavos INTEGER CHECK (diaria_centavos BETWEEN 0 AND 100000000);
