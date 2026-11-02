"""Conservative starting profiles, not machine- or fabric-certified settings."""
import copy,hashlib,json
PROFILES={
 'thin':dict(label='Dunne stof — algemeen',spacing=.50,multiplier=1.15,pull=.05,area=12,under='edge',under_spacing=4,tip='Lichte passende versteviging; proefborduur om plooien te beoordelen.'),
 'standard':dict(label='Standaard stofdikte',spacing=.40,multiplier=1,pull=.10,area=8,under='edge_fill',under_spacing=3,tip='Kies versteviging passend bij rek en dichtheid van het ontwerp.'),
 'canvas':dict(label='Dikke stof — canvas',spacing=.45,multiplier=1,pull=.10,area=20,under='edge',under_spacing=4,tip='Een stevige stof vraagt doorgaans minder ondersteuning; controleer naald en proeflap.'),
 'felt':dict(label='Vilt',spacing=.42,multiplier=1,pull=.10,area=6,under='edge_fill',under_spacing=3,tip='Test op hetzelfde vilt; dikte en stevigheid verschillen.'),
 'fleece':dict(label='Fleece / hoogpolige stof',spacing=.40,multiplier=1,pull=.25,area=2,under='edge_fill',under_spacing=2,tip='Passende versteviging en een geschikte topping helpen voorkomen dat steken in de pool verdwijnen.')}

# Numeric values are conservative BorduurStudio starting values for 40 wt thread,
# not a machine-certified material recipe. Keep old keys for saved projects.
PROFILES.update({
 'terry':dict(label='Badstof — handdoek',spacing=.40,multiplier=1,pull=.30,area=2,under='edge_fill',under_spacing=2,length=5.0,stabilizer='Passende cut-away of stevige tear-away onder de handdoek.',topping='Wateroplosbare folie bovenop tegen het wegzakken in de lussen.',needle='Borduurnaald 75/11–90/14 passend bij dikte en garen.',tip='Zet de pool vast met onderlaag en topping; span de handdoek zonder de lussen plat te drukken.'),
 'satin_fabric':dict(label='Satijn — stof',spacing=.50,multiplier=1,pull=.05,area=12,under='edge',under_spacing=4,length=2.5,stabilizer='Lichte geschikte versteviging; bij gladde stof een zelfklevende of tijdelijk gefixeerde steun.',topping='Gewoonlijk geen topping nodig.',needle='Fijne borduur- of microtexnaald passend bij de stof.',tip='Lichte onderlaag en minder dichte vulling beperken plooien; vermijd afdrukken van de ring.'),
 'jersey':dict(label='Tricot — T-shirt / jersey',spacing=.45,multiplier=1,pull=.20,area=4,under='edge_fill',under_spacing=3,length=2.5,stabilizer='Zachte cut-away of no-show mesh; stevig genoeg voor de rek.',topping='Optioneel dunne wateroplosbare folie bij een ruwe structuur.',needle='Jersey-/borduurnaald met ronde punt; stretchnaald voor sterk rekbare tricot.',tip='Niet uitrekken bij inspannen. Blijvende versteviging helpt de vorm na het wassen te behouden.'),
 'polyester':dict(label='Polyester — geweven stof',spacing=.45,multiplier=1,pull=.15,area=8,under='edge',under_spacing=3,length=2.5,stabilizer='Versteviging passend bij dikte: lichte cut-away of tear-away voor stabiele geweven stof.',topping='Gewoonlijk geen topping nodig.',needle='Fijne borduur- of microtexnaald passend bij de geweven stof.',tip='Dit profiel is voor geweven polyester. Kies tricot of lycra voor rekbare polyester; let op warmtegevoeligheid.'),
 'lycra':dict(label='Lycra — zeer rekbare stof',spacing=.50,multiplier=1,pull=.25,area=4,under='edge_fill',under_spacing=3.5,length=2.5,stabilizer='Zachte maar stabiele cut-away of no-show mesh, passend bij sterke rek.',topping='Optioneel dunne wateroplosbare folie.',needle='Stretchnaald passend bij de stof, vaak 75/11.',tip='Span zonder rek; gebruik lichte ontwerpen. Dichte grote vlakken beperken de rekbaarheid.'),
 'denim':dict(label='Jeans — denim',spacing=.45,multiplier=1,pull=.10,area=20,under='edge',under_spacing=4,length=3,stabilizer='Tear-away voor stabiele denim; cut-away bij stretchdenim of een zwaar ontwerp.',topping='Gewoonlijk geen topping nodig.',needle='Borduurnaald passend bij denimdikte en garen; test dikkere naden apart.',tip='Een stevige stof heeft minder onderlaag nodig. Kies bij sterk rekbare stretchjeans het tricotprofiel.'),
 'velour':dict(label='Velours — poolstof',spacing=.42,multiplier=1,pull=.25,area=2,under='edge_fill',under_spacing=2,length=2.5,stabilizer='Cut-away of geschikte zelfklevende versteviging; steun kiezen op basis van rek.',topping='Wateroplosbare folie bovenop om de pool vrij te houden van de steken.',needle='Fijne borduurnaald; bij rekbare velours een geschikte jersey-/stretchnaald.',tip='Voorkom ringafdrukken: fixeer op de versteviging zonder de pool in de ring plat te drukken. Test de vleugrichting.')
})

def describe(key):
    p=PROFILES[key]
    under='lichte contouronderlaag' if p['under']=='edge' else 'contour + grove steunvulling'
    text=f"Minimum rijafstand {p['spacing']:.2f} mm; trekcompensatie minimaal {p['pull']:.2f} mm. Onderlaag: {under}, vanaf {p['area']:g} mm²."
    if p.get('length'):text+=f" Steeklengte maximaal {p['length']:g} mm."
    for field,label in [('stabilizer','Versteviging'),('topping','Topping'),('needle','Naald')]:
        if p.get(field):text+='\n'+label+': '+p[field]
    return text+'\n'+p['tip']+'\nStartwaarden voor normaal borduurgaren: eerst proefborduren en zo nodig aanpassen.'

def apply(objects,key):
    if key not in PROFILES:raise ValueError('Kies een geldig stofprofiel.')
    profile=PROFILES[key];out=copy.deepcopy(objects)
    for obj in out:
        if obj.get('fill') in ('fill','both','satin','zigzag','column','satin_fill'):
            if not obj.get('outline_settings'):
                obj['spacing']=min(1.5,max(profile['spacing'],float(obj['spacing'])*profile['multiplier']))
                obj['compensation']=max(float(obj.get('compensation',0)),profile['pull'])
            if profile.get('length'):obj['length']=min(float(obj['length']),profile['length'])
            obj['underlay']=False;obj['fabric_underlay']=profile['under'];obj['fabric_underlay_area']=profile['area'];obj['fabric_underlay_spacing']=profile['under_spacing']
        # Single/triple outline stitches don't need a second sewn outline.
    return out

def fingerprint(pattern):
    data=[pattern.stitches,[t.color for t in pattern.threadlist]]
    return hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()
