CREATE TABLE IF NOT EXISTS transactions (
  id CHAR(36) PRIMARY KEY,
  valor DECIMAL(10,2) NOT NULL,
  categoria ENUM('ganho','gasto') NOT NULL,
  data DATE NOT NULL,
  descricao VARCHAR(255),
  status ENUM('Pago','Pendente','Atrasado') DEFAULT 'Pago'
);