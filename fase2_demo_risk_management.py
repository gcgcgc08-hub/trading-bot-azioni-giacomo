"""
FASE 2 - Demo del risk management
====================================

Questo script NON compra o vende nulla per davvero: prende dei numeri di
esempio e mostra come funzionano le tre funzioni di risk_management.py,
cosi' possiamo controllare insieme che i calcoli abbiano senso, prima di
usarle sul serio dentro la prima strategia vera (Fase 3).
"""

from risk_management import (
    calcola_stop_loss,
    calcola_dimensione_posizione,
    controlla_limite_perdita_giornaliera,
)

print("=== Esempio 1: stop loss e dimensione della posizione ===\n")

# Immaginiamo di voler comprare un'azione che oggi costa 150$
prezzo_entrata = 150.0
capitale_totale = 100_000.0  # il saldo del tuo conto paper

stop_loss = calcola_stop_loss(prezzo_entrata)
print(f"Prezzo di entrata:    {prezzo_entrata:>10,.2f} $")
print(f"Stop loss calcolato:  {stop_loss:>10,.2f} $  (vendiamo se scende sotto questo prezzo)")

risultato = calcola_dimensione_posizione(capitale_totale, prezzo_entrata, stop_loss)
print(f"\nCon un capitale di {capitale_totale:,.2f} $, rischiando l'1% per trade:")
print(f"  Azioni da comprare:                {risultato['numero_azioni']}")
print(f"  Costo totale della posizione:      {risultato['costo_totale']:>10,.2f} $")
print(f"  Perdita massima stimata (se stop): {risultato['perdita_massima_stimata']:>10,.2f} $")


print("\n=== Esempio 2: limite di perdita giornaliera (circuit breaker) ===\n")

valore_stamattina = 100_000.0
valore_adesso = 96_500.0  # ipotizziamo una brutta giornata

deve_fermarsi, perdita = controlla_limite_perdita_giornaliera(valore_stamattina, valore_adesso)
print(f"Valore portafoglio stamattina: {valore_stamattina:>10,.2f} $")
print(f"Valore portafoglio adesso:     {valore_adesso:>10,.2f} $")
print(f"Perdita di oggi:               {perdita * 100:>9.2f}%")
print(f"Il bot dovrebbe fermarsi?      {'SI' if deve_fermarsi else 'No'}")
