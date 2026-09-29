var McPanelBundle=(function(g){"use strict";/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const O=globalThis,j=O.ShadowRoot&&(O.ShadyCSS===void 0||O.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,B=Symbol(),F=new WeakMap;let Z=class{constructor(t,e,r){if(this._$cssResult$=!0,r!==B)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(j&&t===void 0){const r=e!==void 0&&e.length===1;r&&(t=F.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),r&&F.set(e,t))}return t}toString(){return this.cssText}};const J=i=>new Z(typeof i=="string"?i:i+"",void 0,B),Y=(i,...t)=>{const e=i.length===1?i[0]:t.reduce((r,s,n)=>r+(o=>{if(o._$cssResult$===!0)return o.cssText;if(typeof o=="number")return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(s)+i[n+1],i[0]);return new Z(e,i,B)},$t=(i,t)=>{if(j)i.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(const e of t){const r=document.createElement("style"),s=O.litNonce;s!==void 0&&r.setAttribute("nonce",s),r.textContent=e.cssText,i.appendChild(r)}},G=j?i=>i:i=>i instanceof CSSStyleSheet?(t=>{let e="";for(const r of t.cssRules)e+=r.cssText;return J(e)})(i):i;/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const{is:gt,defineProperty:bt,getOwnPropertyDescriptor:_t,getOwnPropertyNames:yt,getOwnPropertySymbols:vt,getPrototypeOf:At}=Object,U=globalThis,Q=U.trustedTypes,xt=Q?Q.emptyScript:"",St=U.reactiveElementPolyfillSupport,E=(i,t)=>i,R={toAttribute(i,t){switch(t){case Boolean:i=i?xt:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,t){let e=i;switch(t){case Boolean:e=i!==null;break;case Number:e=i===null?null:Number(i);break;case Object:case Array:try{e=JSON.parse(i)}catch{e=null}}return e}},D=(i,t)=>!gt(i,t),X={attribute:!0,type:String,converter:R,reflect:!1,useDefault:!1,hasChanged:D};Symbol.metadata??=Symbol("metadata"),U.litPropertyMetadata??=new WeakMap;let v=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=X){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const r=Symbol(),s=this.getPropertyDescriptor(t,r,e);s!==void 0&&bt(this.prototype,t,s)}}static getPropertyDescriptor(t,e,r){const{get:s,set:n}=_t(this.prototype,t)??{get(){return this[e]},set(o){this[e]=o}};return{get:s,set(o){const c=s?.call(this);n?.call(this,o),this.requestUpdate(t,c,r)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??X}static _$Ei(){if(this.hasOwnProperty(E("elementProperties")))return;const t=At(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(E("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(E("properties"))){const e=this.properties,r=[...yt(e),...vt(e)];for(const s of r)this.createProperty(s,e[s])}const t=this[Symbol.metadata];if(t!==null){const e=litPropertyMetadata.get(t);if(e!==void 0)for(const[r,s]of e)this.elementProperties.set(r,s)}this._$Eh=new Map;for(const[e,r]of this.elementProperties){const s=this._$Eu(e,r);s!==void 0&&this._$Eh.set(s,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const r=new Set(t.flat(1/0).reverse());for(const s of r)e.unshift(G(s))}else t!==void 0&&e.push(G(t));return e}static _$Eu(t,e){const r=e.attribute;return r===!1?void 0:typeof r=="string"?r:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const r of e.keys())this.hasOwnProperty(r)&&(t.set(r,this[r]),delete this[r]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return $t(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,r){this._$AK(t,r)}_$ET(t,e){const r=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,r);if(s!==void 0&&r.reflect===!0){const n=(r.converter?.toAttribute!==void 0?r.converter:R).toAttribute(e,r.type);this._$Em=t,n==null?this.removeAttribute(s):this.setAttribute(s,n),this._$Em=null}}_$AK(t,e){const r=this.constructor,s=r._$Eh.get(t);if(s!==void 0&&this._$Em!==s){const n=r.getPropertyOptions(s),o=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:R;this._$Em=s;const c=o.fromAttribute(e,n.type);this[s]=c??this._$Ej?.get(s)??c,this._$Em=null}}requestUpdate(t,e,r,s=!1,n){if(t!==void 0){const o=this.constructor;if(s===!1&&(n=this[t]),r??=o.getPropertyOptions(t),!((r.hasChanged??D)(n,e)||r.useDefault&&r.reflect&&n===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,r))))return;this.C(t,e,r)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:r,reflect:s,wrapped:n},o){r&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),n!==!0||o!==void 0)||(this._$AL.has(t)||(this.hasUpdated||r||(e=void 0),this._$AL.set(t,e)),s===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}const t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[s,n]of this._$Ep)this[s]=n;this._$Ep=void 0}const r=this.constructor.elementProperties;if(r.size>0)for(const[s,n]of r){const{wrapped:o}=n,c=this[s];o!==!0||this._$AL.has(s)||c===void 0||this.C(s,void 0,n,c)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(e)):this._$EM()}catch(r){throw t=!1,this._$EM(),r}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[E("elementProperties")]=new Map,v[E("finalized")]=new Map,St?.({ReactiveElement:v}),(U.reactiveElementVersions??=[]).push("2.1.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const I=globalThis,tt=i=>i,H=I.trustedTypes,et=H?H.createPolicy("lit-html",{createHTML:i=>i}):void 0,rt="$lit$",m=`lit$${Math.random().toFixed(9).slice(2)}$`,st="?"+m,Et=`<${st}>`,b=document,w=()=>b.createComment(""),P=i=>i===null||typeof i!="object"&&typeof i!="function",L=Array.isArray,wt=i=>L(i)||typeof i?.[Symbol.iterator]=="function",q=`[ 	
\f\r]`,C=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,it=/-->/g,nt=/>/g,_=RegExp(`>|${q}(?:([^\\s"'>=/]+)(${q}*=${q}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),ot=/'/g,at=/"/g,ct=/^(?:script|style|textarea|title)$/i,Pt=i=>(t,...e)=>({_$litType$:i,strings:t,values:e}),W=Pt(1),A=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),ht=new WeakMap,y=b.createTreeWalker(b,129);function lt(i,t){if(!L(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return et!==void 0?et.createHTML(t):t}const Ct=(i,t)=>{const e=i.length-1,r=[];let s,n=t===2?"<svg>":t===3?"<math>":"",o=C;for(let c=0;c<e;c++){const a=i[c];let p,u,h=-1,f=0;for(;f<a.length&&(o.lastIndex=f,u=o.exec(a),u!==null);)f=o.lastIndex,o===C?u[1]==="!--"?o=it:u[1]!==void 0?o=nt:u[2]!==void 0?(ct.test(u[2])&&(s=RegExp("</"+u[2],"g")),o=_):u[3]!==void 0&&(o=_):o===_?u[0]===">"?(o=s??C,h=-1):u[1]===void 0?h=-2:(h=o.lastIndex-u[2].length,p=u[1],o=u[3]===void 0?_:u[3]==='"'?at:ot):o===at||o===ot?o=_:o===it||o===nt?o=C:(o=_,s=void 0);const $=o===_&&i[c+1].startsWith("/>")?" ":"";n+=o===C?a+Et:h>=0?(r.push(p),a.slice(0,h)+rt+a.slice(h)+m+$):a+m+(h===-2?c:$)}return[lt(i,n+(i[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),r]};class k{constructor({strings:t,_$litType$:e},r){let s;this.parts=[];let n=0,o=0;const c=t.length-1,a=this.parts,[p,u]=Ct(t,e);if(this.el=k.createElement(p,r),y.currentNode=this.el.content,e===2||e===3){const h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(s=y.nextNode())!==null&&a.length<c;){if(s.nodeType===1){if(s.hasAttributes())for(const h of s.getAttributeNames())if(h.endsWith(rt)){const f=u[o++],$=s.getAttribute(h).split(m),z=/([.?@])?(.*)/.exec(f);a.push({type:1,index:n,name:z[2],strings:$,ctor:z[1]==="."?Tt:z[1]==="?"?Mt:z[1]==="@"?Ot:N}),s.removeAttribute(h)}else h.startsWith(m)&&(a.push({type:6,index:n}),s.removeAttribute(h));if(ct.test(s.tagName)){const h=s.textContent.split(m),f=h.length-1;if(f>0){s.textContent=H?H.emptyScript:"";for(let $=0;$<f;$++)s.append(h[$],w()),y.nextNode(),a.push({type:2,index:++n});s.append(h[f],w())}}}else if(s.nodeType===8)if(s.data===st)a.push({type:2,index:n});else{let h=-1;for(;(h=s.data.indexOf(m,h+1))!==-1;)a.push({type:7,index:n}),h+=m.length-1}n++}}static createElement(t,e){const r=b.createElement("template");return r.innerHTML=t,r}}function x(i,t,e=i,r){if(t===A)return t;let s=r!==void 0?e._$Co?.[r]:e._$Cl;const n=P(t)?void 0:t._$litDirective$;return s?.constructor!==n&&(s?._$AO?.(!1),n===void 0?s=void 0:(s=new n(i),s._$AT(i,e,r)),r!==void 0?(e._$Co??=[])[r]=s:e._$Cl=s),s!==void 0&&(t=x(i,s._$AS(i,t.values),s,r)),t}class kt{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:r}=this._$AD,s=(t?.creationScope??b).importNode(e,!0);y.currentNode=s;let n=y.nextNode(),o=0,c=0,a=r[0];for(;a!==void 0;){if(o===a.index){let p;a.type===2?p=new T(n,n.nextSibling,this,t):a.type===1?p=new a.ctor(n,a.name,a.strings,this,t):a.type===6&&(p=new Ut(n,this,t)),this._$AV.push(p),a=r[++c]}o!==a?.index&&(n=y.nextNode(),o++)}return y.currentNode=b,s}p(t){let e=0;for(const r of this._$AV)r!==void 0&&(r.strings!==void 0?(r._$AI(t,r,e),e+=r.strings.length-2):r._$AI(t[e])),e++}}class T{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,r,s){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=r,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=x(this,t,e),P(t)?t===l||t==null||t===""?(this._$AH!==l&&this._$AR(),this._$AH=l):t!==this._$AH&&t!==A&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):wt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==l&&P(this._$AH)?this._$AA.nextSibling.data=t:this.T(b.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:r}=t,s=typeof r=="number"?this._$AC(t):(r.el===void 0&&(r.el=k.createElement(lt(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===s)this._$AH.p(e);else{const n=new kt(s,this),o=n.u(this.options);n.p(e),this.T(o),this._$AH=n}}_$AC(t){let e=ht.get(t.strings);return e===void 0&&ht.set(t.strings,e=new k(t)),e}k(t){L(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let r,s=0;for(const n of t)s===e.length?e.push(r=new T(this.O(w()),this.O(w()),this,this.options)):r=e[s],r._$AI(n),s++;s<e.length&&(this._$AR(r&&r._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const r=tt(t).nextSibling;tt(t).remove(),t=r}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}}class N{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,r,s,n){this.type=1,this._$AH=l,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=n,r.length>2||r[0]!==""||r[1]!==""?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=l}_$AI(t,e=this,r,s){const n=this.strings;let o=!1;if(n===void 0)t=x(this,t,e,0),o=!P(t)||t!==this._$AH&&t!==A,o&&(this._$AH=t);else{const c=t;let a,p;for(t=n[0],a=0;a<n.length-1;a++)p=x(this,c[r+a],e,a),p===A&&(p=this._$AH[a]),o||=!P(p)||p!==this._$AH[a],p===l?t=l:t!==l&&(t+=(p??"")+n[a+1]),this._$AH[a]=p}o&&!s&&this.j(t)}j(t){t===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class Tt extends N{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===l?void 0:t}}class Mt extends N{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==l)}}class Ot extends N{constructor(t,e,r,s,n){super(t,e,r,s,n),this.type=5}_$AI(t,e=this){if((t=x(this,t,e,0)??l)===A)return;const r=this._$AH,s=t===l&&r!==l||t.capture!==r.capture||t.once!==r.once||t.passive!==r.passive,n=t!==l&&(r===l||s);s&&this.element.removeEventListener(this.name,this,r),n&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class Ut{constructor(t,e,r){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(t){x(this,t)}}const Rt=I.litHtmlPolyfillSupport;Rt?.(k,T),(I.litHtmlVersions??=[]).push("3.3.3");const Ht=(i,t,e)=>{const r=e?.renderBefore??t;let s=r._$litPart$;if(s===void 0){const n=e?.renderBefore??null;r._$litPart$=s=new T(t.insertBefore(w(),n),n,void 0,e??{})}return s._$AI(i),s};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const K=globalThis;class S extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Ht(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return A}}S._$litElement$=!0,S.finalized=!0,K.litElementHydrateSupport?.({LitElement:S});const Nt=K.litElementPolyfillSupport;Nt?.({LitElement:S}),(K.litElementVersions??=[]).push("4.2.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const zt={attribute:!0,type:String,converter:R,reflect:!1,hasChanged:D},jt=(i=zt,t,e)=>{const{kind:r,metadata:s}=e;let n=globalThis.litPropertyMetadata.get(s);if(n===void 0&&globalThis.litPropertyMetadata.set(s,n=new Map),r==="setter"&&((i=Object.create(i)).wrapped=!0),n.set(e.name,i),r==="accessor"){const{name:o}=e;return{set(c){const a=t.get.call(this);t.set.call(this,c),this.requestUpdate(o,a,i,!0,c)},init(c){return c!==void 0&&this.C(o,void 0,i,c),c}}}if(r==="setter"){const{name:o}=e;return function(c){const a=this[o];t.call(this,c),this.requestUpdate(o,a,i,!0,c)}}throw Error("Unsupported decorator location: "+r)};function dt(i){return(t,e)=>typeof e=="object"?jt(i,t,e):((r,s,n)=>{const o=s.hasOwnProperty(n);return s.constructor.createProperty(n,r),o?Object.getOwnPropertyDescriptor(s,n):void 0})(i,t,e)}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function pt(i){return dt({...i,state:!0,attribute:!1})}const ut=`
  :host {
    display: block;
    height: 100%;
    overflow: auto;
    background: var(--mc-bg-primary);
    color: var(--mc-text-primary);
    font-family: "Share Tech Mono", var(--primary-font-family, ui-monospace, system-ui, sans-serif);
    --ac-cyan: var(--mc-accent, #00e5ff);
    --ac-magenta: var(--mc-magenta, #ff2bd6);
    --ac-scan: rgba(0, 229, 255, 0.09);
  }
  .wrap {
    max-width: 980px;
    margin: 0 auto;
    padding: 1rem 1.25rem 3rem;
  }

  .page-header,
  header.page-header {
    display: flex;
    align-items: flex-end;
    gap: 16px;
    padding-bottom: 12px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--mc-border-subtle);
    box-shadow: 0 0 18px rgba(0, 229, 255, 0.12);
    background-image: repeating-linear-gradient(
      180deg,
      transparent,
      transparent 2px,
      var(--ac-scan) 3px
    );
  }
  .page-header h1,
  h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-shadow: 0 0 12px rgba(0, 229, 255, 0.35);
  }
  .sub {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--mc-text-secondary);
  }
  .header-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: var(--mc-gap-card);
  }
  .card,
  .zone-card,
  .item,
  .pi-card {
    background: var(--mc-bg-card);
    border: 1px solid var(--mc-border-subtle);
    border-radius: var(--mc-radius-card);
    padding: var(--mc-pad-card);
    box-shadow: 0 0 10px rgba(0, 229, 255, 0.08);
  }
  .card--empty {
    border-color: rgba(255, 107, 107, 0.35);
  }
  .card h2,
  .card-header {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .card-body {
    margin-top: 10px;
  }

  label {
    display: block;
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--mc-text-secondary);
    margin: 10px 0 4px;
  }
  input,
  select,
  textarea {
    width: 100%;
    box-sizing: border-box;
    font-family: inherit;
    font-size: 14px;
    background: var(--mc-bg-secondary);
    color: var(--mc-text-primary);
    border: 1px solid var(--mc-border-input);
    border-radius: var(--mc-radius-input);
    padding: 8px 10px;
    transition: border-color 0.15s;
  }
  input:focus,
  select:focus,
  textarea:focus {
    outline: none;
    border-color: var(--mc-accent);
  }

  .btn-primary,
  .btn.btn-primary {
    background: var(--mc-accent);
    color: var(--mc-bg-primary);
    border: 0;
    border-radius: var(--mc-radius-btn);
    padding: 8px 16px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }
  .btn-primary:hover {
    opacity: 0.88;
  }

  .btn-ghost,
  .btn-secondary,
  .btn.btn-secondary {
    background: transparent;
    color: var(--mc-accent);
    border: 1px solid color-mix(in srgb, var(--mc-accent) 40%, transparent);
    border-radius: var(--mc-radius-btn);
    padding: 6px 12px;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }
  .btn-ghost:hover,
  .btn-secondary:hover {
    background: color-mix(in srgb, var(--mc-accent) 10%, transparent);
  }

  .btn {
    padding: 8px 18px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 0.9rem;
    font-family: inherit;
  }
  .btn-danger {
    background: transparent;
    color: var(--mc-color-err);
    border: 1px solid var(--mc-color-err);
  }
  .btn-link {
    background: transparent;
    color: var(--mc-accent);
    padding: 4px 8px;
  }

  .feedback {
    font-size: 13px;
    min-height: 18px;
  }
  .feedback.ok {
    color: var(--mc-color-ok);
  }
  .feedback.err {
    color: var(--mc-color-err);
  }
  .feedback.warn {
    color: var(--mc-color-warn);
  }

  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
  }
  .empty {
    color: var(--mc-text-secondary);
    padding: 32px;
    text-align: center;
  }
  .badge {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .badge--empty {
    color: var(--mc-color-err);
    margin-left: auto;
  }
  .hint {
    color: var(--mc-text-secondary);
    font-size: 0.85rem;
  }
`,Bt=J(ut);function ft(){return ut}const d={bgPrimary:"var(--primary-background-color, #0b1020)",bgCard:"var(--card-background-color, #12192e)",bgSecondary:"var(--secondary-background-color, #0d1426)",textPrimary:"var(--primary-text-color, #e8eefc)",textSecondary:"var(--secondary-text-color, #9aa8c7)",accent:"var(--primary-color, #00e5ff)",magenta:"#ff2bd6",borderSubtle:"rgba(255,255,255,0.08)",borderInput:"rgba(255,255,255,0.12)",colorOk:"#7dffb3",colorErr:"#ff6b8a",colorWarn:"#ffd770",radiusCard:"10px",radiusInput:"6px",radiusBtn:"6px",gapCard:"14px",padCard:"16px"};function Dt(i){if(i.__mcPanelTokensInjected)return;const t=document.createElement("style");t.textContent=`:root {
  --mc-bg-primary:    ${d.bgPrimary};
  --mc-bg-card:       ${d.bgCard};
  --mc-bg-secondary:  ${d.bgSecondary};
  --mc-text-primary:  ${d.textPrimary};
  --mc-text-secondary:${d.textSecondary};
  --mc-accent:        ${d.accent};
  --mc-magenta:       ${d.magenta};
  --mc-border-subtle: ${d.borderSubtle};
  --mc-border-input:  ${d.borderInput};
  --mc-color-ok:      ${d.colorOk};
  --mc-color-err:     ${d.colorErr};
  --mc-color-warn:    ${d.colorWarn};
  --mc-radius-card:   ${d.radiusCard};
  --mc-radius-input:  ${d.radiusInput};
  --mc-radius-btn:    ${d.radiusBtn};
  --mc-gap-card:      ${d.gapCard};
  --mc-pad-card:      ${d.padCard};
  --ac-cyan:          ${d.accent};
  --ac-magenta:       ${d.magenta};
  --ac-scan:          rgba(0, 229, 255, 0.09);
}`,document.head.appendChild(t),i.__mcPanelTokensInjected=!0}var It=Object.defineProperty,V=(i,t,e,r)=>{for(var s=void 0,n=i.length-1,o;n>=0;n--)(o=i[n])&&(s=o(t,e,s)||s);return s&&It(t,e,s),s};class M extends S{constructor(){super(...arguments),this.hass=null,this._feedbackMsg="",this._feedbackKind="",this.legacyPaint=!1,this._initialized=!1,this._fbTimer=null}static{this.styles=[Bt]}static sharedStyles(){return ft()}createRenderRoot(){const t=super.createRenderRoot();if(this.legacyPaint&&t instanceof ShadowRoot){const e=new CSSStyleSheet;e.replaceSync(ft()),t.adoptedStyleSheets=[...t.adoptedStyleSheets,e]}return t}update(t){if(this.legacyPaint){if(t.has("hass")&&this.hass&&!this._initialized){this._initialized=!0;const r=this;r._render?.(),r._boot?.()}Object.getPrototypeOf(S.prototype).update.call(this,t);return}super.update(t)}updated(t){this.legacyPaint||t.has("hass")&&this.hass&&!this._initialized&&(this._initialized=!0,this._boot?.())}disconnectedCallback(){super.disconnectedCallback(),this._initialized=!1,this._fbTimer&&clearTimeout(this._fbTimer)}async _boot(){}_esc(t){return String(t??"").replace(/[&<>"']/g,e=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[e])}_feedback(t,e="ok"){if(this._fbTimer&&clearTimeout(this._fbTimer),this._feedbackMsg=t,this._feedbackKind=e,this.legacyPaint){const r=this.renderRoot.querySelector("#feedback");r&&(r.textContent=t,r.className=`feedback ${e}`)}e==="ok"&&(this._fbTimer=setTimeout(()=>this._clearFeedback(),3e3))}_clearFeedback(){if(this._fbTimer&&clearTimeout(this._fbTimer),this._fbTimer=null,this._feedbackMsg="",this._feedbackKind="",this.legacyPaint){const t=this.renderRoot.querySelector("#feedback");t&&(t.textContent="",t.className="feedback")}}_feedbackTemplate(){const t=this._feedbackKind?` ${this._feedbackKind}`:"";return W`<span id="feedback" class="feedback${t}"
      >${this._feedbackMsg}</span
    >`}render(){return l}}V([dt({attribute:!1})],M.prototype,"hass"),V([pt()],M.prototype,"_feedbackMsg"),V([pt()],M.prototype,"_feedbackKind");const mt=typeof window<"u"?window:globalThis;return Dt(mt),mt.McPanel={Base:M,tokens:d,html:W,css:Y,nothing:l},g.McPanelBase=M,g.css=Y,g.html=W,g.nothing=l,g.tokens=d,Object.defineProperty(g,Symbol.toStringTag,{value:"Module"}),g})({});
//# sourceMappingURL=mc-panel.js.map
