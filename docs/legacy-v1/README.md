# Prima iterazione — package YAML

Sostituita dal custom component `access_control`.

**Non installare questi file insieme al componente.** L automazione del package
si aggancia anch essa all evento `tag_scanned`: ogni lettura verrebbe valutata
due volte e il lettore riceverebbe due risposte, potenzialmente in disaccordo.

Restano qui come riferimento: la macchina a stati e i sensori "cosa farebbe
adesso e perche" sono passati nel componente quasi invariati.
