/**
 * Script de Automatización - Capa 3
 * Ejecuta de forma secuencial las pruebas de las enmiendas XLS-65 y XLS-66.
 */

const { execSync } = require('child_process');
const path = require('path');

function runAudits() {
    console.log("=========================================");
    console.log(" INICIANDO AUDITORÍA TÉCNICA - XRPL ");
    console.log("=========================================\n");

    const evaluators = [
        path.join(__dirname, '../evaluator/test_xls65.js'),
        path.join(__dirname, '../evaluator/test_xls66.js')
    ];

    for (const evaluator of evaluators) {
        console.log(`[RUNNER] Ejecutando: ${path.basename(evaluator)}`);
        try {
            execSync(`node "${evaluator}"`, { stdio: 'inherit' });
            console.log("");
        } catch (error) {
            console.error(`\n[FAIL] La auditoría falló en ${path.basename(evaluator)}\n`);
            process.exit(1);
        }
    }

    console.log("=========================================");
    console.log(" [SUCCESS] ¡Todas las auditorías pasaron con éxito! ");
    console.log("=========================================");
}

runAudits();