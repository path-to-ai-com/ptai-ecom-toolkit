// Synthetisches Theme-Skript für die Tests von theme.apps.
// Ein Kommentar wie // document.location darf keinen Host ergeben.
class WishlistLink {
  constructor() {
    this.endpoint = "/apps/beispiel-proxy/wishlist";
  }
  load() {
    return fetch(this.endpoint).then((response) => response.json());
  }
}
window.WishlistLink = WishlistLink;
