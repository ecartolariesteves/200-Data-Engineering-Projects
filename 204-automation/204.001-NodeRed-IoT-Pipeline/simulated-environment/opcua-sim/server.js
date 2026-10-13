const { OPCUAServer, DataType, StatusCodes, Variant, DataValue } = require("node-opcua");

/**
 * Servidor OPC UA simulado · Sofrel/LACROIX
 *
 * Simula un dispositivo Sofrel con:
 * - Variable HValue (la que se usa en producción)
 * - Source Timestamp diferido (simula datos que llegan en batch con retraso)
 * - Vuelta de contador aleatoria (~5% probabilidad)
 */
async function main() {
  const server = new OPCUAServer({
    port: 4840,
    resourcePath: "/UA/SofrelSim",
    buildInfo: {
      productName: "Sofrel Simulator",
      buildNumber: "1.0.0",
    }
  });

  await server.initialize();
  console.log("Servidor OPC UA inicializado");

  const addressSpace = server.engine.addressSpace;
  const namespace = addressSpace.getOwnNamespace();

  // Dispositivo simulado
  const device = namespace.addObject({
    organizedBy: addressSpace.rootFolder.objects,
    browseName: "SofrelCounter001",
  });

  let counterValue = 10000; // valor inicial del contador

  // HValue: valor histórico con Source Timestamp diferido
  // En producción: SIEMPRE leer HValue, nunca Value
  // Los datos llegan en batch desde el campo con retraso de horas
  namespace.addVariable({
    componentOf: device,
    browseName: "HValue",
    dataType: DataType.Double,
    minimumSamplingInterval: 1000,
    value: {
      timestamped_get() {
        // Simular vuelta de contador (~5% probabilidad)
        if (Math.random() < 0.05) {
          console.log(`[VUELTA DE CONTADOR] ${counterValue} → 0`);
          counterValue = Math.floor(Math.random() * 100);
        } else {
          counterValue += Math.floor(Math.random() * 10);
        }

        // Source Timestamp diferido: entre 0 y 2 horas atrás
        // Simula datos de campo que llegan en batch con retraso
        const sourceTimestamp = new Date(
          Date.now() - Math.random() * 2 * 3600 * 1000
        );

        console.log(
          `[HValue] value=${counterValue} sourceTS=${sourceTimestamp.toISOString()}`
        );

        return new DataValue({
          value: new Variant({ dataType: DataType.Double, value: counterValue }),
          sourceTimestamp: sourceTimestamp,
          serverTimestamp: new Date(),
          statusCode: StatusCodes.Good,
        });
      },
    },
  });

  await server.start();

  console.log("");
  console.log("========================================");
  console.log("  Servidor OPC UA simulado · Sofrel     ");
  console.log("========================================");
  console.log(`  Endpoint: opc.tcp://localhost:4840     `);
  console.log(`  Nodo:     SofrelCounter001.HValue      `);
  console.log("========================================");
  console.log("  Presiona Ctrl+C para detener          ");
  console.log("");
}

main().catch((err) => {
  console.error("Error arrancando servidor OPC UA:", err);
  process.exit(1);
});
