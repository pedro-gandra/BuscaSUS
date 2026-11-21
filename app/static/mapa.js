(function () {
  var BH = [-19.92, -43.94];

  function lerJson(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function criarMapa(idElemento) {
    var el = document.getElementById(idElemento);
    if (!el || typeof L === "undefined") return null;
    var mapa = L.map(el).setView(BH, 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(mapa);
    return mapa;
  }

  function marcador(p, link) {
    var m = L.marker([p.lat, p.lon]);
    var caixa = document.createElement("div");
    if (link) {
      var a = document.createElement("a");
      a.href = "/estabelecimento/" + encodeURIComponent(p.id);
      a.textContent = p.nome;
      caixa.appendChild(a);
    } else {
      caixa.textContent = p.nome;
    }
    return m.bindPopup(caixa);
  }

  // Página de resultados
  var mapa = criarMapa("mapa");
  if (mapa) {
    var pontos = lerJson("pontos") || [];
    var usuario = lerJson("usuario");
    var grupo = L.featureGroup();
    pontos.forEach(function (p) { marcador(p, true).addTo(grupo); });
    grupo.addTo(mapa);
    if (usuario) {
      L.circleMarker([usuario.lat, usuario.lon], { radius: 9, color: "#d1242f", fillOpacity: 0.8 })
        .bindPopup("Você está aqui").addTo(mapa);
      mapa.setView([usuario.lat, usuario.lon], 14);
    } else if (pontos.length) {
      mapa.fitBounds(grupo.getBounds(), { padding: [20, 20], maxZoom: 16 });
    }
  }

  // Página de detalhes
  var pequeno = criarMapa("mapa-pequeno");
  if (pequeno) {
    var p = lerJson("ponto");
    if (p) {
      marcador(p, false).addTo(pequeno);
      pequeno.setView([p.lat, p.lon], 16);
    }
  }

  // "Perto de mim"
  var botao = document.getElementById("perto-de-mim");
  if (botao) {
    botao.addEventListener("click", function () {
      var msg = document.getElementById("msg-geo");
      if (!navigator.geolocation) {
        msg.textContent = "Seu navegador não permite localização.";
        return;
      }
      msg.textContent = "Obtendo sua localização…";
      navigator.geolocation.getCurrentPosition(function (pos) {
        var params = new URLSearchParams(window.location.search);
        params.set("lat", pos.coords.latitude.toFixed(4));
        params.set("lon", pos.coords.longitude.toFixed(4));
        params.set("ordem", "distancia");
        window.location.assign("/busca?" + params.toString());
      }, function () {
        msg.textContent = "Não foi possível obter sua localização. Verifique a permissão do navegador.";
      }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 });
    });
  }
})();
